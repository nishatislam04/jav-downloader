"""Proxy remote thumbnails for the web UI (avoids hotlink / CORS blocks)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from jav_downloader.sites.base import _http_get

_ALLOWED = re.compile(r'^https?://', re.I)


def fetch_thumbnail(image_url: str) -> tuple[bytes, str]:
    """Fetch image bytes and content-type for a remote thumbnail URL."""
    url = str(image_url or '').strip()
    if not _ALLOWED.match(url):
        raise ValueError('Invalid thumbnail URL')

    parsed = urlparse(url)
    referer = f'{parsed.scheme}://{parsed.netloc}/'
    headers = {'Referer': referer, 'Accept': 'image/*,*/*;q=0.8'}
    if 'jav.guru' in parsed.netloc:
        headers['Referer'] = 'https://jav.guru/'

    resp = _http_get(url, headers, timeout=20)
    status = getattr(resp, 'status_code', 0)
    if status != 200:
        raise ValueError(f'Thumbnail fetch failed (HTTP {status})')

    content = getattr(resp, 'content', b'') or b''
    if not content:
        raise ValueError('Empty thumbnail response')

    ctype = str(getattr(resp, 'headers', {}).get('Content-Type') or 'image/jpeg')
    return content, ctype.split(';', 1)[0].strip() or 'image/jpeg'
