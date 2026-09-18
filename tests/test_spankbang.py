import sys
import types

import pytest


def _stub_runtime_dependency(name, factory=None):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory() if factory else types.ModuleType(name)


def _cloudscraper_stub():
    mod = types.ModuleType('cloudscraper')

    def create_scraper(*args, **kwargs):
        raise AssertionError('cloudscraper should not be used by offline tests')

    mod.create_scraper = create_scraper
    return mod


def _m3u8_stub():
    mod = types.ModuleType('m3u8')
    mod.load = lambda *args, **kwargs: None
    mod.loads = lambda *a, **k: types.SimpleNamespace(playlists=[], segments=[], keys=[])
    return mod


_stub_runtime_dependency('cloudscraper', _cloudscraper_stub)
_stub_runtime_dependency('m3u8', _m3u8_stub)

from uav_downloader.sites import spankbang as spankbang_mod
from uav_downloader.sites.spankbang import (
    SiteSpankBang,
    _extract_stream_key,
    _extract_title,
    _sources_from_api,
    _sources_from_inline,
)


def _sample_page_html(stream_key='MTQzNjA3NTYuMzY45ATDrMbTOFI5-1ositKPF8jw'):
    return f"""
    <html><head>
      <meta property="og:title" content="Example JAV Title： Porn" />
      <meta property="og:image" content="https://cdn.example/poster.jpg" />
    </head><body>
      <h1 class="text-primary" data-testid="video-title">Example JAV Title</h1>
      <div data-streamkey="{stream_key}"></div>
    </body></html>
    """


def test_spankbang_validate_url_is_anchored():
    ok = ('https://spankbang.com/a575a/video/brazzers+sara+retali+and+mariana+martix+'
          'turn+a+casual+visit+into+a+squirting+threesome')
    assert SiteSpankBang.validate_url(ok) == 'a575a'
    assert SiteSpankBang.validate_url('https://spankbang.com/s/jav/') is None
    assert SiteSpankBang.validate_url('https://spankbang.com/a575a/playlist/hot') is None
    assert SiteSpankBang.validate_url('https://jav.guru/1/example/') is None


def test_extract_stream_key_from_data_attribute():
    html_text = _sample_page_html('abc123-token')
    assert _extract_stream_key(html_text) == 'abc123-token'


def test_sources_from_inline_parses_mp4_urls():
    html_text = """
    <script>
    stream_url_720p = "https://cdn.example/17038702-720p.mp4?secure=x";
    stream_url_1080p = "https://cdn.example/17038702-1080p.mp4?secure=x";
    stream_url_m3u8_1080p = "https://cdn.example/master.m3u8";
    </script>
    """
    sources = _sources_from_inline(html_text)
    assert [item['label'] for item in sources] == ['720p', '1080p']
    assert sources[0]['height'] == 720
    assert sources[1]['height'] == 1080


def test_sources_from_api_skips_m3u8_and_empty_lists():
    class FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {
                '240p': ['https://cdn.example/17038702-240p.mp4?secure=x'],
                '480p': [],
                '720p': ['https://cdn.example/17038702-720p.mp4?secure=x'],
                '1080p': ['https://cdn.example/17038702-1080p.mp4?secure=x'],
                '4k': [],
                'm3u8_720p': ['https://cdn.example/master.m3u8'],
                'cover_image': 'https://cdn.example/cover.jpg',
                'length': 1234,
            }

    class FakeScraper:
        @staticmethod
        def post(url, data, headers, timeout, **kwargs):
            assert url.endswith('/api/videos/stream')
            assert data['id'] == 'stream-key'
            return FakeResp()

    sources = _sources_from_api(
        FakeScraper(), 'stream-key', 'https://spankbang.com/a575a/video/example')
    labels = [item['label'] for item in sources]
    assert labels == ['240p', '720p', '1080p']
    assert sources[-1]['height'] == 1080


def test_extract_title_prefers_og_and_strips_suffix():
    from bs4 import BeautifulSoup

    html_text = _sample_page_html()
    soup = BeautifulSoup(html_text, 'html.parser')
    assert _extract_title(soup, html_text) == 'Example JAV Title'


def test_get_url_infos_uses_stream_api_when_inline_missing(monkeypatch):
    page_html = _sample_page_html()

    class FakeResp:
        def __init__(self, text='', status_code=200):
            self.text = text
            self.status_code = status_code
            self.content = text.encode()
            self.headers = {}

        def json(self):
            return {
                '720p': ['https://cdn.example/17038702-720p.mp4?secure=x'],
                '1080p': ['https://cdn.example/17038702-1080p.mp4?secure=x'],
            }

    class FakeScraper:
        cookies = types.SimpleNamespace(set=lambda *a, **k: None)

        def get(self, url, **kwargs):
            if url == 'https://spankbang.com/':
                return FakeResp(status_code=200)
            raise AssertionError(f'unexpected get url {url}')

        def post(self, url, **kwargs):
            return FakeResp()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(spankbang_mod, '_make_scraper', lambda: FakeScraper())
    monkeypatch.setattr(
        spankbang_mod,
        'fetch_with_mirrors',
        lambda scraper, url, site_key, validate, timeout=30, headers_factory=None: (
            FakeResp(text=page_html), 'spankbang.com', 'ok'),
    )

    crawler = SiteSpankBang.__new__(SiteSpankBang)
    crawler.silence = True
    crawler._url = 'https://spankbang.com/a575a/video/example-title'
    crawler.get_url_infos()
    assert crawler._direct_url == 'https://cdn.example/17038702-1080p.mp4?secure=x'
    assert crawler._direct_referer == 'https://spankbang.com/'
    assert crawler._targetName == 'Example JAV Title'
    assert crawler._imageUrl == 'https://cdn.example/poster.jpg'
