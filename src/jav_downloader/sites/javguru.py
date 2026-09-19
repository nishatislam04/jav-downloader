#!/usr/bin/env python
# coding: utf-8

import base64
import html
import json
import os
import random
import re
import string
import time
from urllib.parse import parse_qs, urljoin, urlsplit

try:
    from curl_cffi import requests as cffi_requests
    _use_cffi = True
except ImportError:
    _use_cffi = False
import cloudscraper
from bs4 import BeautifulSoup

from jav_downloader.core import config
from jav_downloader.sites.base import (
    M3U8Crawler,
    MirrorsBlockedError,
    fetch_with_mirrors,
    request_headers,
    speed_limiter,
    _get_session,
    _is_cf_interstitial,
)
from jav_downloader.sites.direct_mp4 import run_direct_download
from jav_downloader.sites.supjav import _strip_fake_header

_BLOCKED_MSG = (
    "jav.guru 被 Cloudflare 阻擋（可能是你的網路/IP 信譽問題，請改用 VPN 或不同網路）")

_SERVER_PRIORITY = ('SB', 'TV', 'VO', 'LU', 'DD', 'JK', 'EA')
_SKIP_SERVERS = frozenset({'AV'})

_JAVCLAN_HOSTS = frozenset({'javclan.com', 'www.javclan.com'})
_TURBOVID_HOSTS = frozenset({'turbovidhls.com', 'www.turbovidhls.com'})
_LULU_HOSTS = frozenset({
    'maxstream.org', 'www.maxstream.org',
    'streamhihi.com', 'www.streamhihi.com',
    'lulustream.com', 'www.lulustream.com',
    'luluvdo.com', 'www.luluvdo.com',
    'luluvdoo.com', 'www.luluvdoo.com',
})
_DOOD_HOST_MARKERS = ('playmogo.com', 'doodstream.com', 'dood.', 'dooood.')

_TITLE_SUFFIX_RE = re.compile(
    r'\s*[⋆✦•·|]\s*Jav\s*Guru\s*[⋆✦•·|]?\s*'
    r'(?:Japanese\s+porn\s+Tube)?\s*$',
    re.I,
)
_SITE_TITLE_SUFFIX_RE = re.compile(
    r'\s*[|⋆✦•·-]\s*(?:Jav\s*Guru|Japanese\s+porn\s+Tube)\s*$',
    re.I,
)


def _make_scraper():
    if _use_cffi:
        return cffi_requests.Session(impersonate='chrome')
    return cloudscraper.create_scraper(browser=request_headers, delay=10)


def _server_label(raw_text):
    text = re.sub(r'\s+', ' ', str(raw_text or '').strip().upper())
    if not text.startswith('STREAM '):
        return None
    label = text.split(' ', 1)[1].strip()
    return label if label and label not in _SKIP_SERVERS else None


def _parse_localize_servers(html_text):
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


def _gateway_url_from_config(config_obj):
    raw = str((config_obj or {}).get('iframe_url') or '').strip()
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


def _embed_file_code(embed_url):
    path = urlsplit(str(embed_url or '')).path.rstrip('/')
    if not path:
        return None
    code = path.rsplit('/', 1)[-1]
    return code or None


def _polish_title(raw_title):
    title = html.unescape(str(raw_title or '')).strip()
    if not title:
        return title
    title = _TITLE_SUFFIX_RE.sub('', title).strip()
    title = _SITE_TITLE_SUFFIX_RE.sub('', title).strip()
    return title


def _format_resolve_errors(errors):
    lines = ['已嘗試的 STREAM 來源：']
    for label, reason in errors:
        lines.append(f'  • STREAM {label}: {reason}')
    lines.append('所有來源均無法取得播放清單或直連 URL。')
    return '\n'.join(lines)


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
    match = re.search(r'https://[^\s"\'\\]+master\.txt[^\s"\'\\]*', text or '')
    if match:
        return match.group(0).replace('\\/', '/')
    return None


def _playlist_from_html(html_text):
    playlist = _extract_m3u8_from_text(html_text)
    if playlist:
        return playlist
    for script in re.findall(r'<script[^>]*>(.*?)</script>', html_text or '', re.S):
        if 'eval(function(p,a,c,k,e,d){while(c--)' not in script:
            continue
        unpacked = _unpack_jw_packer(script)
        playlist = _pick_streamhg_playlist(unpacked) or _extract_m3u8_from_text(unpacked or '')
        if playlist:
            return playlist
    return None


def _extract_title(soup, html_text):
    og = re.search(r'og:title"\s+content="([^"]+)"', html_text or '')
    if og:
        return _polish_title(og.group(1))
    if soup.title:
        return _polish_title(soup.title.get_text(strip=True))
    return ''


def _extract_thumbnail(soup, html_text):
    for selector in (
        'meta[property="og:image"]',
        'meta[name="og:image"]',
        'meta[name="twitter:image"]',
        'meta[property="twitter:image"]',
    ):
        tag = soup.select_one(selector)
        content = tag.get('content') if tag else None
        if content:
            return html.unescape(str(content).strip())

    for pattern in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'og:image["\']?\s+content=["\']([^"\']+)["\']',
    ):
        match = re.search(pattern, html_text or '', re.I)
        if match:
            return html.unescape(match.group(1).strip())

    for match in re.finditer(
            r'var\s+\w+\s*=\s*(\{.*?\})\s*;', html_text or '', re.S):
        try:
            cfg = json.loads(match.group(1))
            raw = str((cfg or {}).get('iframe_url') or '').strip()
            if not raw:
                continue
            gateway = base64.b64decode(raw).decode('utf-8', errors='ignore')
            for key in ('bg', 'poster', 'img', 'image'):
                values = parse_qs(urlsplit(gateway).query).get(key)
                if not values:
                    continue
                raw = html.unescape(str(values[0]).strip())
                if raw.startswith('http'):
                    return raw
                if raw.startswith('//'):
                    return f'https:{raw}'
                if raw.startswith('/'):
                    return f'https://jav.guru{raw}'
        except Exception:
            continue

    for selector in (
        'img.wp-post-image',
        '.post-thumbnail img',
        '.inside-article img',
        'article img',
        '.entry-content img',
        'img[src*="upload"]',
    ):
        img = soup.select_one(selector)
        if not img:
            continue
        for attr in ('src', 'data-src', 'data-lazy-src', 'data-original'):
            src = str(img.get(attr) or '').strip()
            if not src or src.startswith('data:'):
                continue
            if src.startswith('//'):
                return f'https:{src}'
            if src.startswith('/'):
                return f'https://jav.guru{src}'
            if src.startswith('http'):
                return src
    return None


def _headers_for_origin(origin):
    origin = str(origin or '').rstrip('/') + '/'
    root = origin.rstrip('/')
    return {'Referer': origin, 'Origin': root}


def _voe_rot13(value):
    out = []
    for char in value:
        if 'A' <= char <= 'Z':
            out.append(chr((ord(char) - 65 + 13) % 26 + 65))
        elif 'a' <= char <= 'z':
            out.append(chr((ord(char) - 97 + 13) % 26 + 97))
        else:
            out.append(char)
    return ''.join(out)


def _voe_replace_patterns(value):
    for pattern in ("@$", "^^", "~@", "%?", "*~", "!!", "#&"):
        value = value.replace(pattern, '_')
    return value


def _voe_decrypt_payload(encoded_string):
    payload = _voe_rot13(encoded_string)
    payload = _voe_replace_patterns(payload)
    payload = payload.replace('_', '')
    payload = base64.b64decode(payload + '=' * (-len(payload) % 4))
    payload = ''.join(chr(ord(char) - 3) for char in payload.decode('latin1'))
    payload = payload[::-1]
    return json.loads(base64.b64decode(payload + '=' * (-len(payload) % 4)))


def _normalize_voe_playlist(source, scraper, headers):
    source = str(source or '').replace('\\/', '/').strip()
    if not source:
        return None
    if source.endswith('.m3u8') or source.endswith('.txt'):
        return source
    candidates = [
        source.rstrip('/') + '/master.m3u8',
        source.rstrip('/') + '/master.txt',
        source.rstrip('/') + '.m3u8',
    ]
    for candidate in candidates:
        try:
            resp = scraper.get(
                candidate,
                headers=headers,
                timeout=20,
                **config.proxy_request_kwargs(),
            )
        except Exception:
            continue
        if getattr(resp, 'status_code', 0) == 200 and '#EXTM3U' in (resp.text or ''):
            return candidate
    return None


def _resolve_voe(scraper, embed_url):
    origin = _embed_origin(embed_url)
    if not origin:
        return None
    headers = _headers_for_origin(origin)
    resp = scraper.get(
        embed_url,
        headers=headers,
        timeout=30,
        allow_redirects=True,
        **config.proxy_request_kwargs(),
    )
    if _is_cf_interstitial(resp):
        raise MirrorsBlockedError(_BLOCKED_MSG)
    text = resp.text
    final_origin = _embed_origin(str(getattr(resp, 'url', embed_url) or embed_url)) or origin
    headers = _headers_for_origin(final_origin)
    redirect = re.search(r"window\.location\.href\s*=\s*'([^']+)';", text)
    if redirect:
        resp = scraper.get(
            redirect.group(1),
            headers=headers,
            timeout=30,
            allow_redirects=True,
            **config.proxy_request_kwargs(),
        )
        if _is_cf_interstitial(resp):
            raise MirrorsBlockedError(_BLOCKED_MSG)
        text = resp.text
        final_origin = _embed_origin(str(getattr(resp, 'url', embed_url) or embed_url)) or final_origin
        headers = _headers_for_origin(final_origin)
    scripts = re.findall(
        r'<script[^>]+type=[\'"]application/json[\'"][^>]*>(.*?)</script>',
        text,
        re.S,
    )
    if not scripts:
        return None
    encoded = scripts[0].strip().split('["', 1)[-1].rsplit('"]', 1)[0]
    try:
        payload = _voe_decrypt_payload(encoded)
    except Exception:
        return None
    source = payload.get('source') or payload.get('direct_access_url')
    playlist = _normalize_voe_playlist(source, scraper, headers)
    if not playlist:
        return None
    return 'hls', playlist, headers


def _is_dood_host(host):
    host = str(host or '').lower()
    return any(marker in host for marker in _DOOD_HOST_MARKERS)


def _looks_like_hls_url(url):
    lowered = str(url or '').lower()
    return any(marker in lowered for marker in ('.m3u8', '.txt', '/master.', '/index-'))


def _hls_playlist_candidates(url):
    text = str(url or '').strip()
    if not text:
        return []
    seen: set[str] = set()
    candidates = [text]
    if '/' in text:
        base, name = text.rsplit('/', 1)
        if name.endswith('.txt'):
            candidates.append(f'{base}/master.m3u8')
            candidates.append(text[:-4] + '.m3u8')
        elif not name.endswith('.m3u8'):
            root = text.rstrip('/')
            candidates.extend([
                f'{root}/master.m3u8',
                f'{root}/master.txt',
                f'{root}.m3u8',
            ])
    out = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def _fetch_playlist_text(scraper, candidate, headers):
    try:
        resp = scraper.get(
            candidate,
            headers=headers,
            timeout=20,
            **config.proxy_request_kwargs(),
        )
    except Exception:
        return None
    if getattr(resp, 'status_code', 0) != 200:
        return None
    text = resp.text or ''
    if '#EXTM3U' not in text:
        return None
    return text


def _probe_hls_playlist(scraper, playlist_url, headers):
    headers = dict(headers or {})
    for candidate in _hls_playlist_candidates(playlist_url):
        text = _fetch_playlist_text(scraper, candidate, headers)
        if not text:
            continue
        if '#EXTINF' in text:
            return candidate
        if '#EXT-X-STREAM-INF' in text:
            try:
                import m3u8
                master = m3u8.loads(text, uri=candidate)
            except Exception:
                continue
            for variant in master.playlists[:4]:
                variant_url = urljoin(candidate, variant.uri)
                variant_text = _fetch_playlist_text(scraper, variant_url, headers)
                if variant_text and '#EXTINF' in variant_text:
                    return candidate
    return None


def _probe_direct_url(scraper, direct_url, headers):
    headers = dict(headers or {})
    try:
        resp = scraper.head(
            direct_url,
            headers=headers,
            timeout=20,
            allow_redirects=True,
            **config.proxy_request_kwargs(),
        )
    except Exception:
        return False
    return getattr(resp, 'status_code', 0) in (200, 206)


def _resolve_doodstream(scraper, embed_url):
    origin = _embed_origin(embed_url)
    if not origin:
        return None
    code = _embed_file_code(embed_url)
    if not code:
        return None
    page_url = embed_url
    if '/d/' in urlsplit(embed_url).path:
        page_url = re.sub(r'/d/', '/e/', embed_url, count=1)
    resp = scraper.get(
        page_url,
        headers=_headers_for_origin(origin),
        timeout=30,
        allow_redirects=True,
        **config.proxy_request_kwargs(),
    )
    if _is_cf_interstitial(resp):
        return None
    text = resp.text
    if 'no_video' in text or 'not found' in text.lower():
        return None
    host = _embed_origin(str(getattr(resp, 'url', page_url) or page_url))
    md5_match = re.search(r'/pass_md5/[^\'"\s<>]+', text)
    if not md5_match:
        return None
    md5_url = host + md5_match.group(0)
    prefix_resp = scraper.get(
        md5_url,
        headers={'Referer': str(getattr(resp, 'url', page_url) or page_url)},
        timeout=30,
        **config.proxy_request_kwargs(),
    )
    if getattr(prefix_resp, 'status_code', 0) != 200:
        return None
    prefix = (prefix_resp.text or '').strip()
    if not prefix.startswith('http'):
        return None
    token = md5_url.rsplit('/', 1)[-1]
    suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    direct_url = f'{prefix}{suffix}?token={token}'
    return 'mp4', direct_url, _headers_for_origin(host)


def _resolve_lulu_embed(scraper, embed_url, page_referer):
    origin = _embed_origin(embed_url)
    code = _embed_file_code(embed_url)
    if not origin or not code:
        return None
    resp = scraper.post(
        f'{origin}/dl',
        data={
            'op': 'embed',
            'file_code': code,
            'auto': '1',
            'referer': page_referer or f'{origin}/',
        },
        headers={
            'Referer': embed_url,
            'Origin': origin,
        },
        timeout=30,
        allow_redirects=True,
        **config.proxy_request_kwargs(),
    )
    if _is_cf_interstitial(resp):
        return None
    text = resp.text or ''
    lowered = text.lower()
    if any(marker in lowered for marker in (
            'no longer available', 'expired', 'embed disabled', 'not found')):
        return None
    playlist = _playlist_from_html(text)
    if not playlist:
        return None
    return 'hls', playlist, _headers_for_origin(origin)


def _resolve_javclan(scraper, embed_url):
    origin = _embed_origin(embed_url) or 'https://javclan.com'
    resp = scraper.get(
        embed_url,
        headers=_headers_for_origin(origin),
        timeout=30,
        allow_redirects=True,
        **config.proxy_request_kwargs(),
    )
    if _is_cf_interstitial(resp):
        raise MirrorsBlockedError(_BLOCKED_MSG)
    final_origin = _embed_origin(str(getattr(resp, 'url', embed_url) or embed_url)) or origin
    playlist = _playlist_from_html(resp.text)
    if not playlist:
        return None
    return 'hls', playlist, _headers_for_origin(final_origin)


def _resolve_turbovidhls(scraper, embed_url):
    origin = _embed_origin(embed_url) or 'https://turbovidhls.com'
    resp = scraper.get(
        embed_url,
        headers=_headers_for_origin(origin),
        timeout=30,
        allow_redirects=True,
        **config.proxy_request_kwargs(),
    )
    if _is_cf_interstitial(resp):
        raise MirrorsBlockedError(_BLOCKED_MSG)
    playlist = _extract_m3u8_from_text(resp.text)
    if not playlist:
        return None
    final_origin = _embed_origin(str(getattr(resp, 'url', embed_url) or embed_url)) or origin
    return 'hls', playlist, _headers_for_origin(final_origin)


def _wrap_hls_resolver(resolver):
    def wrapped(scraper, embed_url):
        result = resolver(scraper, embed_url)
        if not result:
            return None
        if isinstance(result, tuple) and len(result) == 3:
            return result
        playlist, headers = result
        return 'hls', playlist, headers
    return wrapped


def _resolve_embed_stream(scraper, embed_url, page_referer):
    host = (urlsplit(embed_url).hostname or '').lower()
    attempts = []

    if host in _JAVCLAN_HOSTS:
        attempts.append(_wrap_hls_resolver(_resolve_javclan))
    if host in _TURBOVID_HOSTS:
        attempts.append(_wrap_hls_resolver(_resolve_turbovidhls))
    attempts.append(_wrap_hls_resolver(_resolve_voe))
    if host in _LULU_HOSTS:
        attempts.append(lambda s, url: _resolve_lulu_embed(s, url, page_referer))
    if _is_dood_host(host):
        attempts.append(_resolve_doodstream)
    attempts.append(lambda s, url: _resolve_lulu_embed(s, url, page_referer))
    attempts.append(_wrap_hls_resolver(_resolve_javclan))
    attempts.append(_wrap_hls_resolver(_resolve_turbovidhls))

    seen = set()
    for resolver in attempts:
        key = getattr(resolver, '__name__', repr(resolver))
        if key in seen:
            continue
        seen.add(key)
        try:
            result = resolver(scraper, embed_url)
        except MirrorsBlockedError:
            raise
        except Exception:
            continue
        if result:
            return result
    return None


class SiteJavGuru(M3U8Crawler):
    website_pattern = r'https://(?:www\.)?jav\.guru/\d+/.+/?$'
    website_dirname_pattern = r'https://(?:www\.)?jav\.guru/(\d+)/.+/?$'
    direct_site_name = 'JavGuru'
    direct_default_referer = 'https://jav.guru/'

    def _transform_segment(self, data):
        if data[:1] == b'\x47':
            return data
        stripped = _strip_fake_header(data)
        return stripped or data

    def get_url_infos(self):
        with _make_scraper() as scraper:
            self._resolve_from_page(scraper)

    def _resolve_from_page(self, scraper, skip_labels=None):
        skip_labels = set(skip_labels or ())

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

        self._targetName = _extract_title(soup, html_text)
        self._imageUrl = _extract_thumbnail(soup, html_text)

        self._direct_url = None
        self._direct_referer = None
        self._m3u8url = None
        self._extra_headers = {}
        errors = []
        for label, token in servers.items():
            if label in skip_labels:
                continue
            cfg = _load_localize_config(html_text, token)
            gateway = _gateway_url_from_config(cfg)
            if not gateway:
                errors.append((label, 'missing gateway config'))
                continue
            stream_redirect = _stream_redirect_url(gateway)
            if not stream_redirect:
                errors.append((label, 'missing searcho token'))
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
                errors.append((label, f'redirect failed ({exc})'))
                continue
            if _is_cf_interstitial(embed_resp):
                errors.append((label, 'blocked by Cloudflare'))
                continue
            embed_url = str(getattr(embed_resp, 'url', '') or '')
            if not embed_url.startswith('http'):
                errors.append((label, 'invalid embed redirect'))
                continue
            embed_host = urlsplit(embed_url).netloc
            try:
                resolved = _resolve_embed_stream(scraper, embed_url, self._url)
            except MirrorsBlockedError:
                raise
            except Exception as exc:
                errors.append((label, f'{embed_host}: {exc}'))
                continue
            if not resolved:
                errors.append((label, f'{embed_host}: no playlist or direct URL'))
                continue

            kind, stream_url, extra = resolved
            if kind == 'mp4' or (kind == 'hls' and not _looks_like_hls_url(stream_url)):
                if not _probe_direct_url(scraper, stream_url, extra):
                    errors.append((label, f'{embed_host}: direct URL unavailable'))
                    continue
                self._direct_url = stream_url
                self._direct_referer = extra.get('Referer') or self.direct_default_referer
                self._m3u8url = None
                mode = 'MP4'
            elif kind == 'hls' and stream_url.startswith('http'):
                probed = _probe_hls_playlist(scraper, stream_url, extra)
                if not probed:
                    errors.append((label, f'{embed_host}: playlist unavailable'))
                    continue
                self._m3u8url = probed
                self._extra_headers = extra
                self._direct_url = None
                mode = 'HLS'
            else:
                errors.append((label, f'{embed_host}: unrecognized stream URL'))
                continue

            self._active_stream_label = label
            self._emit_job_log(f'Selected STREAM {label} ({embed_host}, {mode})')
            if not self.silence:
                print(
                    f'[JavGuru] 使用 STREAM {label} ({embed_host}, {mode})',
                    flush=True)
            return True

        if skip_labels:
            return False
        raise Exception(_format_resolve_errors(errors))

    def is_url_vaildate(self):
        return bool(self._m3u8url or getattr(self, '_direct_url', None))

    def start_download(self):
        tried: set[str] = set()
        last_error: Exception | None = None
        while True:
            try:
                if getattr(self, '_direct_url', None):
                    return run_direct_download(self)
                if self._m3u8url:
                    return super().start_download()
                raise Exception('no stream configured')
            except Exception as exc:
                last_error = exc
                label = getattr(self, '_active_stream_label', None)
                if label:
                    tried.add(label)
                self._emit_job_log(f'STREAM {label or "?"} failed: {exc}')
                with _make_scraper() as scraper:
                    if not self._resolve_from_page(scraper, skip_labels=tried):
                        break
                self._emit_job_log('Trying next stream mirror…')
                if not self.silence and label:
                    print(
                        f'[JavGuru] STREAM {label} failed ({exc}); trying next source',
                        flush=True,
                    )
        if last_error is not None:
            raise last_error
        raise Exception('no stream configured')
