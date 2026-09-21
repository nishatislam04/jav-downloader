#!/usr/bin/env python
# coding: utf-8
"""Hanime1.me direct-MP4 downloader."""

import html
import re
from urllib.parse import urljoin, urlsplit

import cloudscraper
try:
    from curl_cffi import requests as cffi_requests
    _use_cffi = True
except ImportError:
    _use_cffi = False
from bs4 import BeautifulSoup

from jav_downloader.core import config
from jav_downloader.sites.base import (
    MirrorsBlockedError,
    get_resolution_pref,
    request_headers,
)
from jav_downloader.sites.supjav import SiteSupJav


HANIME1_ROOT = 'https://hanime1.me'
HANIME1_HOME = HANIME1_ROOT + '/'
_BLOCKED_STATUS = frozenset({403, 429, 503})

def _make_scraper():
    """Return a browser-fingerprint session able to establish Hanime1 cookies."""
    if _use_cffi:
        return cffi_requests.Session(impersonate='chrome')
    return cloudscraper.create_scraper(browser=request_headers, delay=10)


def _blocked_response(response) -> bool:
    status = int(getattr(response, 'status_code', 0) or 0)
    if status in _BLOCKED_STATUS:
        return True
    body = str(getattr(response, 'text', '') or '')[:20000].casefold()
    return ('attention required' in body or 'just a moment' in body or
            'cf-chl-' in body)


def _request(session, url, *, timeout=30):
    response = session.get(
        url,
        headers={'Referer': HANIME1_HOME},
        timeout=timeout,
        allow_redirects=True,
        **config.proxy_request_kwargs(),
    )
    if _blocked_response(response):
        raise MirrorsBlockedError(url)
    return response


def _prime_session(session):
    """Visit the homepage first; Hanime1 issues both XSRF and session cookies there."""
    response = _request(session, HANIME1_HOME)
    if int(getattr(response, 'status_code', 0) or 0) != 200:
        raise Exception(f'Hanime1 初始化失敗 (HTTP {response.status_code})')
    return session


def _mp4_height(url, label=''):
    value = f'{label} {url}'
    match = re.search(r'(?<!\d)(\d{3,4})\s*p(?!\w)', value, re.I)
    return int(match.group(1)) if match else None


def _extract_sources(soup):
    """Extract fresh signed progressive-MP4 sources from watch/download markup."""
    sources = []
    seen = set()

    def _add(raw_url, label=''):
        url = html.unescape(str(raw_url or '').strip()).replace('\\/', '/')
        try:
            parsed = urlsplit(url)
        except ValueError:
            return
        if (parsed.scheme.casefold() != 'https' or not parsed.hostname or
                not parsed.path.casefold().endswith('.mp4') or url in seen):
            return
        seen.add(url)
        sources.append({'url': url, 'height': _mp4_height(url, label)})

    for element in soup.select('source[src], a[data-url], a[href]'):
        raw_url = element.get('src') or element.get('data-url') or element.get('href')
        _add(raw_url, element.get_text(' ', strip=True))

    # Keep a conservative fallback for MP4 URLs embedded in inline JSON/JavaScript.
    markup = html.unescape(str(soup)).replace('\\/', '/')
    for raw_url in re.findall(r'https://[^\s\'"<>]+?\.mp4(?:\?[^\s\'"<>]*)?', markup, re.I):
        _add(raw_url)
    return sources


def _select_source(sources, preference):
    """Apply the same highest/lowest/target-or-below policy as HLS variants."""
    items = list(sources or [])
    if not items:
        return None
    known = [item for item in items if isinstance(item.get('height'), int)]
    pref = str(preference or '').strip().casefold()
    if pref == 'lowest':
        return min(known, key=lambda item: item['height']) if known else items[0]
    if pref in {'1080', '720', '480', '360'}:
        if not known:
            return items[0]
        target = int(pref)
        at_or_below = [item for item in known if item['height'] <= target]
        if at_or_below:
            return max(at_or_below, key=lambda item: item['height'])
        return min(known, key=lambda item: item['height'])
    return max(known, key=lambda item: item['height']) if known else items[0]


def _clean_text(value):
    return ' '.join(html.unescape(str(value or '')).replace('\xa0', ' ').split())


def _extract_title(soup):
    heading = soup.select_one('h3.video-details-wrapper')
    if heading:
        title = _clean_text(heading.get_text(' ', strip=True))
        if title:
            return title
    meta = soup.select_one('meta[property="og:title"][content]')
    title = _clean_text(meta.get('content')) if meta else ''
    title = re.sub(r'\s+-\s+Hanime1\.me\s*$', '', title, flags=re.I)
    if title:
        return title
    return _clean_text(soup.title.get_text(' ', strip=True) if soup.title else '')


def _extract_image(soup):
    meta = soup.select_one('meta[property="og:image"][content]')
    raw = meta.get('content') if meta else ''
    if not raw:
        video = soup.select_one('video[poster]')
        raw = video.get('poster') if video else ''
    image_url = urljoin(HANIME1_HOME, html.unescape(str(raw or '').strip()))
    try:
        return image_url if urlsplit(image_url).scheme.casefold() == 'https' else None
    except ValueError:
        return None


class SiteHanime1(SiteSupJav):
    website_pattern = r'https://(?:www\.)?hanime1\.me/watch\?v=\d+$'
    website_dirname_pattern = r'https://(?:www\.)?hanime1\.me/watch\?v=(\d+)$'
    direct_site_name = 'Hanime1'
    direct_default_referer = HANIME1_HOME

    def get_url_infos(self):
        self._direct_url = None
        self._direct_referer = None
        self._m3u8url = None
        with _make_scraper() as scraper:
            _prime_session(scraper)
            response = _request(scraper, self._url)
            status = int(getattr(response, 'status_code', 0) or 0)
            if status != 200:
                raise Exception(f'Hanime1 影片頁讀取失敗 (HTTP {status})')
            soup = BeautifulSoup(response.content, 'html.parser')
            sources = _extract_sources(soup)

            # Older/alternate pages may put the signed URLs only on /download.
            if not sources:
                video_id = self.validate_url(self._url)
                download_url = f'{HANIME1_ROOT}/download?v={video_id}'
                download_response = _request(scraper, download_url)
                download_status = int(
                    getattr(download_response, 'status_code', 0) or 0)
                if download_status == 200:
                    sources = _extract_sources(BeautifulSoup(
                        download_response.content, 'html.parser'))

        selected = _select_source(sources, get_resolution_pref())
        if not selected:
            raise Exception('此 Hanime1 影片目前沒有可用的 MP4 下載來源')
        title = _extract_title(soup)
        if not title:
            raise Exception('Hanime1 影片標題解析失敗（版面可能已改版）')
        self._targetName = title
        self._imageUrl = _extract_image(soup)
        self._direct_url = selected['url']
        self._direct_referer = self._url
        self._extra_headers = {'Referer': self._url}
