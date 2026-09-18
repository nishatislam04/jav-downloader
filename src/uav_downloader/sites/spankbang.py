#!/usr/bin/env python
# coding: utf-8

import html
import re
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
)
from uav_downloader.sites.direct_mp4 import run_direct_download
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
    try:
        scraper.get(
            _ROOT,
            headers={'Referer': _ROOT},
            timeout=30,
            allow_redirects=True,
            **config.proxy_request_kwargs(),
        )
    except Exception:
        pass
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

    length = payload.get('length')
    duration_sec = None
    if length not in (None, ''):
        try:
            duration_sec = float(length)
        except (TypeError, ValueError):
            duration_sec = None

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
    return sources, duration_sec


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
            stream_key = _extract_stream_key(html_text)
            sources = _sources_from_inline(html_text)
            duration_sec = None
            if not sources:
                if not stream_key:
                    raise Exception('找不到 SpankBang stream key（版面改版？）')
                sources, duration_sec = _sources_from_api(
                    scraper, stream_key, self._url)
            elif stream_key:
                try:
                    _, duration_sec = _sources_from_api(
                        scraper, stream_key, self._url)
                except Exception:
                    duration_sec = None
            if duration_sec is not None:
                self._duration_sec = duration_sec

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
            return run_direct_download(self)
        return super().start_download()
