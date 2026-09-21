#!/usr/bin/env python
# coding: utf-8

import re
import html
import os
import time
import concurrent.futures
import cloudscraper
try:
    from curl_cffi import requests as cffi_requests
    _use_cffi = True
except ImportError:
    _use_cffi = False
import threading as _threading
from urllib.parse import urlsplit
from jav_downloader.sites.base import *
from jav_downloader.sites.base import _get_session
from jav_downloader.sites.missav import _unpack_js_eval
from bs4 import BeautifulSoup
from jav_downloader.core import config


SUPREMEJAV = 'https://lk1.supremejav.com/supjav.php?c={}'
_BLOCKED_MSG = "所有鏡像都被 Cloudflare 阻擋（可能是你的網路/IP 信譽問題，請改用 VPN 或不同網路）"
_DIRECT_RANGE_WORKERS = 4
_DIRECT_RANGE_RETRIES = 4
_DIRECT_RETRY_BASE_DELAY = 1.0

def _make_scraper():
    """Fresh scraper: curl_cffi (Cloudflare-capable) if available, else cloudscraper."""
    if _use_cffi:
        return cffi_requests.Session(impersonate='chrome')
    return cloudscraper.create_scraper(browser=request_headers, delay=10)


def _extract_tv_link(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    for a in soup.select('a[data-link]'):
        if a.get_text(strip=True) == 'TV':
            return a.get('data-link', '')
    return None


def _extract_m3u8(body):
    body = body.replace('\\/', '/')
    m = re.search(r'urlPlay[\s=:\'"]+(?P<u>https?://[^\s\'"\\]+\.m3u8[^\s\'"\\]*)', body)
    if m:
        return m.group('u')
    m = re.search(r'https?://[^\s\'"\\]+\.m3u8[^\s\'"\\]*', body)
    return m.group(0) if m else None


def _extract_title(soup):
    h1 = soup.find('h1')
    return h1.get_text(strip=True) if h1 else (soup.title.get_text(strip=True) if soup.title else '')


def _strip_fake_header(data):
    """SupJav segments are MPEG-TS hidden behind a fake PNG header. Return the stream
    from the first valid MPEG-TS sync (0x47 on a 188-byte stride). Plain TS is returned unchanged."""
    if data[:1] == b'\x47':
        return data
    limit = min(len(data) - 188 * 4 - 1, 8000)
    i = 0
    while 0 <= i <= limit:
        j = data.find(b'\x47', i)
        if j < 0 or j > limit:
            break
        if all(data[j + 188 * n] == 0x47 for n in range(5)):
            return data[j:]
        i = j + 1
    return b''


def _server_links(html_text):
    """Return {SERVER_NAME: data_link} for every .btn-server anchor on a SupJav
    video page. Names seen: TV, FST, ST (Streamtape), VOE."""
    soup = BeautifulSoup(html_text, 'html.parser')
    out = {}
    for a in soup.select('a.btn-server[data-link]'):
        name = a.get_text(strip=True).upper()
        link = a.get('data-link', '')
        if name and link and name not in out:
            out[name] = link
    return out


def _streamtape_direct_url(html_text):
    """Extract the direct progressive-MP4 URL from a Streamtape embed page.
    Streamtape overwrites #robotlink via JS:  'PREFIX' + ('SUFFIX').substring(a)[.substring(b)]
    — the static div text is a decoy; only the JS-computed value carries the live token."""
    m = re.search(
        r"getElementById\(\s*['\"]robotlink['\"]\s*\)\.innerHTML\s*=\s*"
        r"['\"]([^'\"]*)['\"]\s*\+\s*(?:['\"]{2}\s*\+\s*)?"
        r"\(\s*['\"]([^'\"]*)['\"]\s*\)((?:\.substring\(\s*\d+\s*\))+)",
        html_text)
    if not m:
        return None
    prefix, suffix, subs = m.group(1), m.group(2), m.group(3)
    s = suffix
    for off in re.findall(r'substring\(\s*(\d+)\s*\)', subs):
        s = s[int(off):]
    link = (prefix + s).lstrip('/')
    if 'get_video' not in link:
        return None
    return 'https://' + link


def _extract_packed_m3u8(html_text):
    """Extract an HLS URL from an fc2stream/FST Dean-Edwards packed script."""
    for script in re.findall(r'<script[^>]*>(.*?)</script>', html_text, re.DOTALL):
        if 'eval(function' not in script or 'm3u8' not in script:
            continue
        unpacked = _unpack_js_eval(script)
        if not unpacked:
            continue
        match = re.search(
            r"https?://[^'\"\\;\s]+\.m3u8[^'\"\\;\s]*",
            unpacked,
        )
        if match:
            return match.group(0)
    return None


def _content_range(value):
    match = re.fullmatch(r'bytes\s+(\d+)-(\d+)/(\d+)', str(value or '').strip(), re.I)
    if not match:
        return None
    start, end, total = (int(part) for part in match.groups())
    if start > end or end >= total:
        return None
    return start, end, total


def _split_byte_ranges(total, workers=_DIRECT_RANGE_WORKERS):
    workers = min(max(1, int(workers)), total)
    chunk, remainder = divmod(total, workers)
    ranges = []
    start = 0
    for index in range(workers):
        size = chunk + (1 if index < remainder else 0)
        end = start + size - 1
        ranges.append((start, end))
        start = end + 1
    return ranges


class SiteSupJav(M3U8Crawler):
    website_pattern = r'https://supjav\.com/(?:(?:zh|ja)/)?\d+\.html$'
    website_dirname_pattern = r'https://supjav\.com/(?:(?:zh|ja)/)?(\d+)\.html$'
    direct_site_name = 'SupJav'
    direct_default_referer = 'https://supjav.com/'

    def _transform_segment(self, data):
        return _strip_fake_header(data)

    _direct_url = None
    _direct_referer = None

    def get_url_infos(self):
        self._direct_url = None
        self._direct_referer = None
        with _make_scraper() as scraper:
            def _validate(resp):
                return 'data-link' in resp.text
            htmlfile, host, reason = fetch_with_mirrors(scraper, self._url, 'supjav', _validate, timeout=30)
            if reason == 'blocked':
                raise MirrorsBlockedError(_BLOCKED_MSG)
            if reason != 'ok':
                raise Exception(f"頁面解析失敗（版面改版或影片不存在）: {self._url}")

            soup = BeautifulSoup(htmlfile.content, 'html.parser')
            servers = _server_links(htmlfile.text)   # {'TV':.., 'ST':.., 'VOE':.., 'FST':..}
            if not servers:
                raise Exception("此影片沒有可用的伺服器來源（版面改版？）")

            m3u8url = None
            m3u8_headers = None
            # 1) FST: downloadable HLS with real 480p/720p/1080p variants (#31).
            if 'FST' in servers:
                try:
                    fst = scraper.get(
                        SUPREMEJAV.format(servers['FST'][::-1]),
                        headers={'Referer': 'https://supjav.com/'},
                        timeout=25,
                        allow_redirects=True,
                        **config.proxy_request_kwargs(),
                    )
                    m3u8url = _extract_packed_m3u8(fst.text)
                    if m3u8url:
                        parts = urlsplit(str(getattr(fst, 'url', '') or ''))
                        origin = (f'{parts.scheme}://{parts.netloc}'
                                  if parts.scheme and parts.netloc else '')
                        m3u8_headers = {'Referer': str(fst.url)}
                        if origin:
                            m3u8_headers['Origin'] = origin
                except MirrorsBlockedError:
                    raise
                except Exception:
                    m3u8url = None
                    m3u8_headers = None

            # 2) Streamtape (ST): progressive MP4 fallback. Resolve it even when FST
            #    works so an HLS failure can downgrade without rescanning the page.
            if 'ST' in servers:
                try:
                    emb = scraper.get(SUPREMEJAV.format(servers['ST'][::-1]),
                                      headers={'Referer': 'https://supjav.com/'},
                                      timeout=25, allow_redirects=True,
                                      **config.proxy_request_kwargs())
                    direct = _streamtape_direct_url(emb.text)
                    if direct:
                        self._direct_url = direct
                        self._direct_referer = str(getattr(emb, 'url', '') or 'https://streamtape.com/')
                except MirrorsBlockedError:
                    raise
                except Exception:
                    pass
            # 3) TV: last HLS fallback (its Google-backed segments often return 429).
            #    Keep it for videos SupJav has not migrated to either FST or ST.
            if not m3u8url and not self._direct_url and 'TV' in servers:
                try:
                    r2 = scraper.get(SUPREMEJAV.format(servers['TV'][::-1]),
                                     headers={'Referer': 'https://supjav.com/'}, timeout=20,
                                     **config.proxy_request_kwargs())
                    if getattr(r2, 'status_code', 0) in (403, 429, 503):
                        raise MirrorsBlockedError(_BLOCKED_MSG)
                    m3u8url = _extract_m3u8(r2.text)
                    if m3u8url:
                        m3u8_headers = {'Referer': 'https://supjav.com/'}
                except MirrorsBlockedError:
                    raise
                except Exception:
                    m3u8url = None

            if not self._direct_url and not m3u8url:
                raise Exception("此影片目前無可用下載來源"
                                "（TV 區段受 Google 限制，且此片無 FST/Streamtape 備援）")

        title = _extract_title(soup)
        self._targetName = html.unescape(title)
        self._imageUrl = None
        self._m3u8url = m3u8url
        self._extra_headers = m3u8_headers or {'Referer': 'https://supjav.com/'}

    def is_url_vaildate(self):
        # The base gate is `True if self._m3u8url` — but a Streamtape source resolves to
        # a direct MP4 (_direct_url) with no m3u8. Without this override the caller would
        # treat the URL as invalid and silently skip it (and __init__ would not sanitize
        # the target filename).
        return bool(self._m3u8url or getattr(self, '_direct_url', None))

    def start_download(self):
        # Prefer FST HLS because it preserves the requested quality (including 1080p).
        # If it fails, automatically downgrade to the Streamtape progressive MP4.
        if self._m3u8url:
            try:
                return super().start_download()
            except Exception:
                if self._cancel_job or not getattr(self, '_direct_url', None):
                    raise
                print('\n[SupJav] FST HLS failed; falling back to Streamtape.', flush=True)
                self.cleanup_temp()
        if getattr(self, '_direct_url', None):
            return self._download_direct()
        return super().start_download()

    @staticmethod
    def _safe_remove(path):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

    def _download_direct(self):
        from jav_downloader.sites.direct_mp4 import run_direct_download
        return run_direct_download(self)

    def _download_direct_ranges(self, part, ref, start_time):
        """Use up to four HTTP Range connections when the host supports ranges.
        The shared requests session mounts SharedSSLAdapter, which is required for every
        concurrent HTTPS path in this project. Return None to keep the serial fallback."""
        session = _get_session()
        probe = None
        try:
            probe = session.get(
                self._direct_url,
                headers={'Referer': ref, 'Range': 'bytes=0-0'},
                timeout=60,
                stream=True,
                allow_redirects=True,
                **config.proxy_request_kwargs(),
            )
            info = _content_range(getattr(probe, 'headers', {}).get('content-range'))
            if getattr(probe, 'status_code', 0) != 206 or not info or info[:2] != (0, 0):
                return None
            total = info[2]
        except Exception:
            return None
        finally:
            if probe is not None:
                try:
                    probe.close()
                except Exception:
                    pass

        ranges = _split_byte_ranges(
            total,
            min(
                _DIRECT_RANGE_WORKERS,
                getattr(self, '_max_workers', _DIRECT_RANGE_WORKERS)))
        if len(ranges) == 1:
            return None

        with open(part, 'wb') as target:
            target.truncate(total)

        progress_lock = _threading.Lock()
        stop_event = _threading.Event()
        done = 0

        def _fetch_range(bounds):
            nonlocal done
            range_start, range_end = bounds
            expected = range_end - range_start + 1
            written = 0
            retries = 0
            while written < expected and not self._cancel_job and not stop_event.is_set():
                cursor = range_start + written
                response = None
                try:
                    response = session.get(
                        self._direct_url,
                        headers={'Referer': ref, 'Range': f'bytes={cursor}-{range_end}'},
                        timeout=60,
                        stream=True,
                        allow_redirects=True,
                        **config.proxy_request_kwargs(),
                    )
                    response_range = _content_range(
                        getattr(response, 'headers', {}).get('content-range'))
                    if (getattr(response, 'status_code', 0) != 206 or
                            response_range != (cursor, range_end, total)):
                        raise Exception("直接下載來源未正確回應分段請求")

                    received = 0
                    with open(part, 'r+b', buffering=0) as target:
                        target.seek(cursor)
                        for chunk in response.iter_content(chunk_size=262144):
                            if self._cancel_job or stop_event.is_set():
                                break
                            if not chunk:
                                continue
                            if written + len(chunk) > expected:
                                raise Exception("直接下載分段長度超出預期")
                            speed_limiter.acquire(len(chunk))
                            if target.write(chunk) != len(chunk):
                                raise Exception("直接下載寫入失敗")
                            written += len(chunk)
                            received += len(chunk)
                            with progress_lock:
                                done += len(chunk)
                                current_done = done
                                elapsed = time.time() - start_time
                                speed = current_done / elapsed if elapsed > 0 else 0
                                if self._progress_callback:
                                    self._progress_callback(current_done, total, speed)

                    if self._cancel_job or stop_event.is_set():
                        break
                    if written < expected:
                        detail = "未收到資料" if received == 0 else "連線提前結束"
                        raise Exception(f"直接下載分段{detail}")
                except Exception:
                    if self._cancel_job or stop_event.is_set():
                        break
                    retries += 1
                    if retries > _DIRECT_RANGE_RETRIES:
                        raise
                    stop_event.wait(_DIRECT_RETRY_BASE_DELAY * retries)
                finally:
                    if response is not None:
                        try:
                            response.close()
                        except Exception:
                            pass

            if not self._cancel_job and not stop_event.is_set() and written != expected:
                raise Exception("直接下載分段不完整（連線中斷？請重試）")
            return written

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(ranges))
        self._t2_executor = executor
        futures = [executor.submit(_fetch_range, bounds) for bounds in ranges]
        try:
            for future in concurrent.futures.as_completed(futures):
                future.result()
        except Exception:
            stop_event.set()
            for future in futures:
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=True)
            self._t2_executor = None

        if self._cancel_job:
            return done, total
        if done != total:
            raise Exception("直接下載不完整（連線中斷？請重試）")
        return done, total

    def _download_direct_serial(self, part, ref, start_time):
        done = os.path.getsize(part) if os.path.exists(part) else 0
        total = 0
        retries = 0
        session = _get_session()
        while not self._cancel_job:
            request_headers = {'Referer': ref}
            if done:
                request_headers['Range'] = f'bytes={done}-'
            resp = None
            try:
                resp = session.get(
                    self._direct_url,
                    headers=request_headers,
                    timeout=60,
                    stream=True,
                    allow_redirects=True,
                    **config.proxy_request_kwargs(),
                )
                status = getattr(resp, 'status_code', 0)
                response_range = _content_range(
                    getattr(resp, 'headers', {}).get('content-range'))
                if done:
                    if status != 206 or not response_range or response_range[0] != done:
                        raise Exception(f"直接續傳失敗 (HTTP {status})")
                    total = response_range[2]
                elif status == 206 and response_range:
                    total = response_range[2]
                elif status == 200:
                    try:
                        total = int(resp.headers.get('content-length') or 0)
                    except Exception:
                        total = 0
                else:
                    raise Exception(f"直接下載失敗 (HTTP {status})")

                received = 0
                with open(part, 'ab' if done else 'wb') as target:
                    for chunk in resp.iter_content(chunk_size=262144):
                        if self._cancel_job:
                            break
                        if not chunk:
                            continue
                        speed_limiter.acquire(len(chunk))
                        target.write(chunk)
                        done += len(chunk)
                        received += len(chunk)
                        elapsed = time.time() - start_time
                        speed = done / elapsed if elapsed > 0 else 0
                        if self._progress_callback and total > 0:
                            self._progress_callback(done, total, speed)

                if self._cancel_job:
                    break
                if total > 0 and done >= total:
                    return done, total
                if total == 0 and received > 0:
                    return done, done
                raise Exception("直接下載連線提前結束")
            except Exception:
                if self._cancel_job:
                    break
                retries += 1
                if retries > _DIRECT_RANGE_RETRIES:
                    raise
                time.sleep(_DIRECT_RETRY_BASE_DELAY * retries)
            finally:
                if resp is not None:
                    try:
                        resp.close()
                    except Exception:
                        pass
        return done, total
