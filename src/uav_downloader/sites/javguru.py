#!/usr/bin/env python
# coding: utf-8

import base64
import html
import json
import re
from urllib.parse import parse_qs, urlsplit

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
    request_headers,
    _is_cf_interstitial,
)
from uav_downloader.sites.supjav import _strip_fake_header

_BLOCKED_MSG = (
    "jav.guru 被 Cloudflare 阻擋（可能是你的網路/IP 信譽問題，請改用 VPN 或不同網路）")

# Prefer hosts that usually resolve to StreamHG / javclan HLS before turbovidhls.
_SERVER_PRIORITY = ('SB', 'TV', 'VO', 'LU', 'DD', 'JK', 'EA')
_SKIP_SERVERS = frozenset({'AV'})

_JAVCLAN_HOSTS = frozenset({'javclan.com', 'www.javclan.com'})
_TURBOVID_HOSTS = frozenset({'turbovidhls.com', 'www.turbovidhls.com'})


def _make_scraper():
    if _use_cffi:
        return cffi_requests.Session(impersonate='chrome')
    return cloudscraper.create_scraper(browser=request_headers, delay=10)


def _get_scraper():
    return _make_scraper()


def _server_label(raw_text):
    text = re.sub(r'\s+', ' ', str(raw_text or '').strip().upper())
    if not text.startswith('STREAM '):
        return None
    label = text.split(' ', 1)[1].strip()
    return label if label and label not in _SKIP_SERVERS else None


def _parse_localize_servers(html_text):
    """Return ordered {label: token} parsed from wp-btn-iframe anchors."""
    soup = BeautifulSoup(html_text, 'html.parser')
    found = {}
    order = []
    for anchor in soup.select('a.wp-btn-iframe__shortcode[data-localize]'):
        label = _server_label(anchor.get_text(' ', strip=True))
        token = str(anchor.get('data-localize') or '').strip()
        if not label or not token or label in found:
            continue
        found[label] = token
        order.append(label)
    servers = {}
    for label in _SERVER_PRIORITY:
        if label in found:
            servers[label] = found[label]
    for label in order:
        if label not in servers:
            servers[label] = found[label]
    return servers


def _load_localize_config(html_text, token):
    match = re.search(
        rf'var\s+{re.escape(token)}\s*=\s*(\{{.*?\}})\s*;',
        html_text,
        re.S,
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _gateway_url_from_config(config):
    raw = str((config or {}).get('iframe_url') or '').strip()
    if not raw:
        return None
    try:
        return base64.b64decode(raw).decode('utf-8', errors='strict')
    except Exception:
        return None


def _token_param_name(gateway_url):
    query = parse_qs(urlsplit(gateway_url).query)
    for key in query:
        if len(key) == 2 and key[1] == 'd' and query[key]:
            return key
    return None


def _stream_redirect_url(gateway_url):
    param = _token_param_name(gateway_url)
    if not param:
        return None
    token = parse_qs(urlsplit(gateway_url).query)[param][0]
    if not token:
        return None
    return f'https://jav.guru/searcho/?{param[0]}r={token[::-1]}'


def _embed_origin(embed_url):
    parts = urlsplit(str(embed_url or ''))
    if parts.scheme and parts.netloc:
        return f'{parts.scheme}://{parts.netloc}'
    return None


def _unpack_jw_packer(script_text):
    match = re.search(
        r"eval\(function\(p,a,c,k,e,d\)\{while\(c--\)if\(k\[c\]\)p=p\.replace\("
        r"new RegExp\('\\\\b'\+c\.toString\(a\)\+'\\\\b','g'\),k\[c\]\);return p\}\("
        r"'(.*?)',\s*(\d+),\s*(\d+),\s*'(.*?)'\.split\('\|'\)",
        script_text,
        re.S,
    )
    if not match:
        return None
    packed, base, count, keys_str = (
        match.group(1), int(match.group(2)), int(match.group(3)), match.group(4).split('|'))
    if base <= 1 or count < 0 or count > 200000:
        return None

    def to_base(number, radix):
        digits = '0123456789abcdefghijklmnopqrstuvwxyz'
        if number == 0:
            return '0'
        out = ''
        while number:
            out = digits[number % radix] + out
            number //= radix
        return out

    lookup = {
        to_base(index, base): (
            keys_str[index] if index < len(keys_str) and keys_str[index]
            else to_base(index, base))
        for index in range(count)
    }
    return re.sub(
        r'\b\w+\b',
        lambda item: lookup.get(item.group(0), item.group(0)),
        packed,
    )


def _pick_streamhg_playlist(unpacked_text):
    if not unpacked_text:
        return None
    for key in ('hls4', 'hls3', 'hls2'):
        match = re.search(rf'"{key}"\s*:\s*"([^"]+)"', unpacked_text)
        if match:
            return match.group(1).replace('\\/', '/')
    return None


def _extract_m3u8_from_text(text):
    match = re.search(r'https://[^\s"\'\\]+\.m3u8[^\s"\'\\]*', text or '')
    if match:
        return match.group(0).replace('\\/', '/')
    return None


def _extract_title(soup, html_text):
    og = re.search(r'og:title"\s+content="([^"]+)"', html_text or '')
    if og:
        return html.unescape(og.group(1))
    if soup.title:
        return html.unescape(soup.title.get_text(strip=True))
    return ''


def _extract_thumbnail(html_text):
    og = re.search(r'og:image"\s+content="([^"]+)"', html_text or '')
    return og.group(1) if og else None


def _resolve_javclan(scraper, embed_url):
    origin = _embed_origin(embed_url) or 'https://javclan.com/'
    resp = scraper.get(
        embed_url,
        headers={'Referer': origin + '/'},
        timeout=30,
        allow_redirects=True,
        **config.proxy_request_kwargs(),
    )
    if _is_cf_interstitial(resp):
        raise MirrorsBlockedError(_BLOCKED_MSG)
    final_url = str(getattr(resp, 'url', embed_url) or embed_url)
    origin = _embed_origin(final_url) or origin
    playlist = None
    for script in re.findall(r'<script[^>]*>(.*?)</script>', resp.text, re.S):
        if 'eval(function(p,a,c,k,e,d){while(c--)' not in script:
            continue
        unpacked = _unpack_jw_packer(script)
        playlist = _pick_streamhg_playlist(unpacked)
        if playlist:
            break
    if not playlist:
        playlist = _extract_m3u8_from_text(resp.text)
    if not playlist:
        return None
    headers_out = {'Referer': origin + '/', 'Origin': origin}
    return playlist, headers_out


def _resolve_turbovidhls(scraper, embed_url):
    origin = _embed_origin(embed_url) or 'https://turbovidhls.com/'
    resp = scraper.get(
        embed_url,
        headers={'Referer': origin + '/'},
        timeout=30,
        allow_redirects=True,
        **config.proxy_request_kwargs(),
    )
    if _is_cf_interstitial(resp):
        raise MirrorsBlockedError(_BLOCKED_MSG)
    playlist = _extract_m3u8_from_text(resp.text)
    if not playlist:
        return None
    origin = _embed_origin(str(getattr(resp, 'url', embed_url) or embed_url)) or origin
    headers_out = {'Referer': origin + '/', 'Origin': origin}
    return playlist, headers_out


def _resolve_generic_embed(scraper, embed_url):
    origin = _embed_origin(embed_url)
    if not origin:
        return None
    resp = scraper.get(
        embed_url,
        headers={'Referer': origin + '/'},
        timeout=30,
        allow_redirects=True,
        **config.proxy_request_kwargs(),
    )
    if _is_cf_interstitial(resp):
        return None
    playlist = _extract_m3u8_from_text(resp.text)
    if not playlist:
        for script in re.findall(r'<script[^>]*>(.*?)</script>', resp.text, re.S):
            if 'eval(function(p,a,c,k,e,d){while(c--)' not in script:
                continue
            unpacked = _unpack_jw_packer(script)
            playlist = _pick_streamhg_playlist(unpacked) or _extract_m3u8_from_text(unpacked or '')
            if playlist:
                break
    if not playlist:
        return None
    final_origin = _embed_origin(str(getattr(resp, 'url', embed_url) or embed_url)) or origin
    return playlist, {'Referer': final_origin + '/', 'Origin': final_origin}


def _resolve_embed_stream(scraper, embed_url):
    host = (urlsplit(embed_url).hostname or '').lower()
    if host in _JAVCLAN_HOSTS:
        return _resolve_javclan(scraper, embed_url)
    if host in _TURBOVID_HOSTS:
        return _resolve_turbovidhls(scraper, embed_url)
    return _resolve_generic_embed(scraper, embed_url)


class SiteJavGuru(M3U8Crawler):
    website_pattern = r'https://(?:www\.)?jav\.guru/\d+/.+/?$'
    website_dirname_pattern = r'https://(?:www\.)?jav\.guru/(\d+)/.+/?$'

    def _transform_segment(self, data):
        if data[:1] == b'\x47':
            return data
        stripped = _strip_fake_header(data)
        return stripped or data

    def get_url_infos(self):
        with _make_scraper() as scraper:
            self._resolve_from_page(scraper)

    def _resolve_from_page(self, scraper):

        def _validate(resp):
            return 'data-localize' in resp.text and 'wp-btn-iframe' in resp.text

        page_resp, host, reason = fetch_with_mirrors(
            scraper, self._url, 'javguru', _validate, timeout=30)
        if reason == 'blocked':
            raise MirrorsBlockedError(_BLOCKED_MSG)
        if reason != 'ok':
            raise Exception(f"頁面解析失敗（版面改版或影片不存在）: {self._url}")

        html_text = page_resp.text
        soup = BeautifulSoup(html_text, 'html.parser')
        servers = _parse_localize_servers(html_text)
        if not servers:
            raise Exception("此影片沒有可用的 STREAM 來源（版面改版？）")

        errors = []
        for label, token in servers.items():
            cfg = _load_localize_config(html_text, token)
            gateway = _gateway_url_from_config(cfg)
            if not gateway:
                errors.append(f'{label}: missing gateway')
                continue
            stream_redirect = _stream_redirect_url(gateway)
            if not stream_redirect:
                errors.append(f'{label}: missing stream token')
                continue
            try:
                embed_resp = scraper.get(
                    stream_redirect,
                    headers={'Referer': self._url},
                    timeout=30,
                    allow_redirects=True,
                    **config.proxy_request_kwargs(),
                )
            except Exception as exc:
                errors.append(f'{label}: redirect failed ({exc})')
                continue
            if _is_cf_interstitial(embed_resp):
                errors.append(f'{label}: blocked by Cloudflare')
                continue
            embed_url = str(getattr(embed_resp, 'url', '') or '')
            if not embed_url.startswith('http'):
                errors.append(f'{label}: invalid embed redirect')
                continue
            try:
                resolved = _resolve_embed_stream(scraper, embed_url)
            except MirrorsBlockedError:
                raise
            except Exception as exc:
                errors.append(f'{label}: {exc}')
                continue
            if not resolved:
                errors.append(f'{label}: no playlist on {urlsplit(embed_url).netloc}')
                continue
            playlist, extra = resolved
            self._m3u8url = playlist
            self._extra_headers = extra
            self._targetName = _extract_title(soup, html_text)
            self._imageUrl = _extract_thumbnail(html_text)
            if not self.silence:
                print(f'[JavGuru] 使用 STREAM {label} ({urlsplit(embed_url).netloc})', flush=True)
            return

        detail = '; '.join(errors[:4])
        if len(errors) > 4:
            detail += f'; +{len(errors) - 4} more'
        raise Exception(
            "此影片目前無可用下載來源"
            f"（已嘗試 {len(servers)} 個 STREAM 選項）"
            + (f": {detail}" if detail else ''))
