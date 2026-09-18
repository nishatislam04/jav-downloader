#!/usr/bin/env python
# coding: utf-8

import html
import os
import re
import time
from urllib.parse import urlsplit

try:
    from curl_cffi import requests as cffi_requests
    _use_cffi = True
except ImportError:
    _use_cffi = False
import cloudscraper
from bs4 import BeautifulSoup

from uav_downloader.core import config
from uav_downloader.sites.base import (
    M3U8Crawler,
    MirrorsBlockedError,
    fetch_with_mirrors,
    get_resolution_pref,
    request_headers,
    speed_limiter,
    _get_session,
)
from uav_downloader.sites.hanime1 import _select_source

_BLOCKED_MSG = (
    "SpankBang 被 Cloudflare 阻擋（可能是你的網路/IP 信譽問題，請改用 VPN 或不同網路）")
_STREAM_API = 'https://spankbang.com/api/videos/stream'
_ROOT = 'https://spankbang.com/'

_STREAM_URL_RE = re.compile(
    r'stream_url_(?P<label>[^\s=]+)\s*=\s*(["\'])(?P<url>(?:(?!\2).)+)\2',
    re.I,
)
_STREAMKEY_RE = re.compile(r'data-streamkey\s*=\s*(["\'])(?P<key>(?:(?!\1).)+)\1', re.I)
_REMOVED_RE = re.compile(
    r'<[^>]+\b(?:id|class)\s*=\s*["\'][^"\']*\bvideo_removed\b',
    re.I,
)
_TITLE_SUFFIX_RES = (
    re.compile(r'\s*[-|]\s*SpankBang\s*$', re.I),
    re.compile(r'\s*[:：]\s*Porn\s*$', re.I),
)


def _make_scraper():
    if _use_cffi:
        return cffi_requests.Session(impersonate='chrome')
    return cloudscraper.create_scraper(browser=request_headers, delay=10)


def _prime_scraper(scraper):
    scraper.cookies.set('country', 'US', domain='.spankbang.com')
    response = scraper.get(
        _ROOT,
        headers={'Referer': _ROOT},
        timeout=30,
        allow_redirects=True,
        **config.proxy_request_kwargs(),
    )
    if int(getattr(response, 'status_code', 0) or 0) != 200:
        raise Exception(f'SpankBang 初始化失敗 (HTTP {response.status_code})')
    return scraper


def _quality_height(label):
    text = str(label or '').strip().casefold()
    if text == '4k':
        return 2160
    match = re.fullmatch(r'(\d{3,4})p', text)
    if match:
        return int(match.group(1))
    return None


def _coerce_url(value):
    if isinstance(value, list):
        value = value[0] if value else None
    url = str(value or '').strip().replace('\\/', '/')
    if url.startswith('http'):
        return url
    return None


def _sources_from_inline(html_text):
    sources = []
    seen = set()
    for match in _STREAM_URL_RE.finditer(str(html_text or '')):
        url = _coerce_url(match.group('url'))
        if not url or url in seen:
            continue
        if '.mp4' not in urlsplit(url).path.casefold():
            continue
        seen.add(url)
        label = match.group('label')
        sources.append({
            'url': url,
            'height': _quality_height(label),
            'label': label,
        })
    return sources


def _sources_from_api(scraper, stream_key, page_url):
    response = scraper.post(
        _STREAM_API,
        data={'id': stream_key, 'data': '0'},
        headers={
            'Referer': page_url,
            'X-Requested-With': 'XMLHttpRequest',
        },
        timeout=30,
        **config.proxy_request_kwargs(),
    )
    status = int(getattr(response, 'status_code', 0) or 0)
    if status != 200:
        raise Exception(f'SpankBang stream API 失敗 (HTTP {status})')
    try:
        payload = response.json()
    except ValueError as exc:
        raise Exception('SpankBang stream API 回傳非 JSON') from exc
    if not isinstance(payload, dict):
        raise Exception('SpankBang stream API 回傳格式異常')

    sources = []
    seen = set()
    for label, raw in payload.items():
        key = str(label or '').strip()
        if not key or key.casefold().startswith('m3u8'):
            continue
        if key in {'cover_image', 'length', 'thumbnail'}:
            continue
        url = _coerce_url(raw)
        if not url or url in seen:
            continue
        path = urlsplit(url).path.casefold()
        if not path.endswith('.mp4') and '.mp4' not in path:
            continue
        seen.add(url)
        sources.append({
            'url': url,
            'height': _quality_height(key),
            'label': key,
        })
    return sources


def _extract_stream_key(html_text):
    match = _STREAMKEY_RE.search(str(html_text or ''))
    return match.group('key').strip() if match else None


def _polish_title(raw_title):
    title = html.unescape(str(raw_title or '')).strip()
    if not title:
        return title
    changed = True
    while changed:
        changed = False
        for pattern in _TITLE_SUFFIX_RES:
            cleaned = pattern.sub('', title).strip()
            if cleaned != title:
                title = cleaned
                changed = True
    return title


def _extract_title(soup, html_text):
    meta = soup.find('meta', property='og:title')
    if meta and meta.get('content'):
        title = _polish_title(meta['content'])
        if title:
            return title

    heading = soup.find('h1', attrs={'data-testid': 'video-title'})
    if heading:
        title = _polish_title(heading.get_text(' ', strip=True))
        if title:
            return title

    match = re.search(
        r'(?s)<h1[^>]+\btitle=["\']([^"\']+)["\']>',
        str(html_text or ''),
    )
    if match:
        return _polish_title(match.group(1))
    return ''


def _extract_thumbnail(soup):
    meta = soup.find('meta', property='og:image')
    if meta and meta.get('content'):
        return html.unescape(meta['content']).strip()
    return None


class SiteSpankBang(M3U8Crawler):
    website_pattern = (
        r'https://(?:[^./]+\.)?spankbang\.com/[\da-z]+/video/.+/?$')
    website_dirname_pattern = (
        r'https://(?:[^./]+\.)?spankbang\.com/(?P<id>[\da-z]+)/video/.+/?$')
    direct_site_name = 'SpankBang'
    direct_default_referer = _ROOT

    def get_url_infos(self):
        self._direct_url = None
        self._direct_referer = None
        self._m3u8url = None
        with _make_scraper() as scraper:
            _prime_scraper(scraper)

            def _validate(resp):
                text = str(getattr(resp, 'text', '') or '')
                return (
                    'data-streamkey' in text
                    or 'stream_url_' in text
                    or 'og:title' in text
                )

            page_resp, host, reason = fetch_with_mirrors(
                scraper,
                self._url,
                'spankbang',
                _validate,
                timeout=30,
                headers_factory=lambda h: {'Referer': f'https://{h}/'},
            )
            if reason == 'blocked':
                raise MirrorsBlockedError(_BLOCKED_MSG)
            if reason != 'ok':
                raise Exception(
                    f'頁面解析失敗（版面改版或影片不存在）: {self._url}')

            html_text = page_resp.text
            if _REMOVED_RE.search(html_text):
                raise Exception('此 SpankBang 影片已被移除或不可用')

            soup = BeautifulSoup(html_text, 'html.parser')
            sources = _sources_from_inline(html_text)
            if not sources:
                stream_key = _extract_stream_key(html_text)
                if not stream_key:
                    raise Exception('找不到 SpankBang stream key（版面改版？）')
                sources = _sources_from_api(scraper, stream_key, self._url)

            selected = _select_source(sources, get_resolution_pref())
            if not selected:
                raise Exception('此 SpankBang 影片目前沒有可用的 MP4 來源')

            title = _extract_title(soup, html_text)
            if not title:
                raise Exception('SpankBang 影片標題解析失敗（版面可能已改版）')

            self._targetName = title
            self._imageUrl = _extract_thumbnail(soup)
            self._direct_url = selected['url']
            self._direct_referer = _ROOT
            self._extra_headers = {'Referer': _ROOT}
            if not self.silence:
                label = selected.get('label') or 'mp4'
                print(
                    f'[SpankBang] 使用 {label} ({urlsplit(selected["url"]).netloc})',
                    flush=True,
                )

    def is_url_vaildate(self):
        return bool(getattr(self, '_direct_url', None) or self._m3u8url)

    def start_download(self):
        if getattr(self, '_direct_url', None):
            return self._download_direct_mp4()
        return super().start_download()

    def _download_direct_mp4(self):
        if self._cancel_job:
            return False
        self._cancel_job = False
        self._create_dest_folder()
        if self.is_target_video_exist():
            print('檔案已存在!!', flush=True)
            return True

        out = self._get_video_savename()
        part = out + '.part'
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass

        referer = self._direct_referer or self.direct_default_referer
        headers = {'Referer': referer}
        start = time.time()
        downloaded = 0
        try:
            resp = _get_session().get(
                self._direct_url,
                headers=headers,
                timeout=60,
                stream=True,
                allow_redirects=True,
                **config.proxy_request_kwargs(),
            )
            if getattr(resp, 'status_code', 0) not in (200, 206):
                raise Exception(
                    f'直接下載失敗 (HTTP {getattr(resp, "status_code", 0)})')
            total = int(resp.headers.get('content-length') or 0)
            with open(part, 'wb') as handle:
                for chunk in resp.iter_content(chunk_size=262144):
                    if self._cancel_job:
                        break
                    if not chunk:
                        continue
                    speed_limiter.acquire(len(chunk))
                    handle.write(chunk)
                    downloaded += len(chunk)
                    elapsed = time.time() - start
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    if total > 0 and self._progress_callback:
                        self._progress_callback(downloaded, total, speed)
        except Exception:
            if os.path.exists(part):
                try:
                    os.remove(part)
                except OSError:
                    pass
            raise

        if self._cancel_job:
            if os.path.exists(part):
                try:
                    os.remove(part)
                except OSError:
                    pass
            return False

        os.replace(part, out)
        print(f'\n下載完成: {os.path.basename(out)}', flush=True)
        return True
