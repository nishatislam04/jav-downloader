import base64
import json
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

from uav_downloader.sites import javguru as javguru_mod
from uav_downloader.sites.javguru import (
    SiteJavGuru,
    _gateway_url_from_config,
    _parse_localize_servers,
    _pick_streamhg_playlist,
    _server_label,
    _stream_redirect_url,
    _token_param_name,
    _unpack_jw_packer,
)


def _sample_page_html():
    iframe_b64 = base64.b64encode(
        b'https://jav.guru/searcho/?xd=83e6b6b66337778627734643&bg=https%3A%2F%2Fexample.test%2Fposter.jpg'
    ).decode()
    config = json.dumps({'iframe_url': iframe_b64})
    return f"""
    <html><head><title>[SNOS-400] Example title</title></head><body>
    <ul>
      <li><a class="wp-btn-iframe__shortcode" data-localize="tok_tv">STREAM TV</a></li>
      <li><a class="wp-btn-iframe__shortcode" data-localize="tok_sb">STREAM SB</a></li>
      <li><a class="wp-btn-iframe__shortcode" data-localize="tok_vo">STREAM VO</a></li>
      <li><a class="wp-btn-iframe__shortcode" data-localize="tok_av">STREAM AV</a></li>
    </ul>
    <script>
    var tok_tv = {config};
    var tok_sb = {config};
    var tok_vo = {config};
    </script>
    </body></html>
    """


def test_javguru_validate_url_is_anchored():
    ok = ('https://jav.guru/1053086/snos-400-right-after-abstinence/'
          'she-turns-into-a-beast-in-an-aphrodisiac-bath-non-stop-ahegao-and-massive-incontinence-riri-nanatsumori/')
    assert SiteJavGuru.validate_url(ok) == '1053086'
    assert SiteJavGuru.validate_url('https://jav.guru/page/2/') is None
    assert SiteJavGuru.validate_url('https://supjav.com/12345.html') is None


def test_server_label_skips_av():
    assert _server_label('STREAM SB') == 'SB'
    assert _server_label('stream tv') == 'TV'
    assert _server_label('STREAM AV') is None


def test_parse_localize_servers_respects_priority_and_skips_av():
    servers = _parse_localize_servers(_sample_page_html())
    assert list(servers.keys()) == ['SB', 'TV', 'VO']
    assert servers['SB'] == 'tok_sb'


def test_stream_redirect_url_reverses_token():
    gateway = _gateway_url_from_config({'iframe_url': base64.b64encode(
        b'https://jav.guru/searcho/?xd=83e6b6b66337778627734643&bg=x').decode()})
    assert _token_param_name(gateway) == 'xd'
    assert _stream_redirect_url(gateway) == (
        'https://jav.guru/searcho/?xr=34643772687773366b6b6e38')


def test_pick_streamhg_playlist_prefers_hls4_then_hls3():
    unpacked = (
        'var links={"hls2":"https://cdn.example/hls2/master.m3u8",'
        '"hls3":"https://cdn.example/hls3/master.txt",'
        '"hls4":"https://cdn.example/hls4/master.txt"};jwplayer();'
    )
    assert _pick_streamhg_playlist(unpacked) == 'https://cdn.example/hls4/master.txt'
    assert _pick_streamhg_playlist(
        'var links={"hls3":"https://cdn.example/hls3/master.txt"};'
    ) == 'https://cdn.example/hls3/master.txt'


def test_unpack_jw_packer_extracts_links():
    script = (
        "eval(function(p,a,c,k,e,d){while(c--)if(k[c])p=p.replace(new RegExp('\\\\b'+"
        "c.toString(a)+'\\\\b','g'),k[c]);return p}('var links={\"hls3\":\"https://"
        "cdn.example/master.txt\"};',62,1,'https://cdn.example/master.txt'.split('|'),0,{}))"
    )
    unpacked = _unpack_jw_packer(script)
    assert unpacked is not None
    assert 'https://cdn.example/master.txt' in unpacked


def test_get_url_infos_uses_first_working_server(monkeypatch):
    page_html = _sample_page_html()

    class FakeResp:
        def __init__(self, text='', url='https://example.test/', status_code=200):
            self.text = text
            self.url = url
            self.status_code = status_code
            self.content = text.encode()
            self.headers = {}

    class FakeScraper:
        def get(self, url, **kwargs):
            if 'searcho/?xr=' in url:
                return FakeResp(url='https://javclan.com/e/demo123')
            if url.endswith('/e/demo123'):
                return FakeResp(
                    text=(
                        '<html><script>eval(function(p,a,c,k,e,d){while(c--)if(k[c])'
                        'p=p.replace(new RegExp(\'\\\\b\'+c.toString(a)+\'\\\\b\',\'g\'),'
                        'k[c]);return p}(\'var links={"hls3":"https://cdn.example/master.txt"};\','
                        '62,1,\'https://cdn.example/master.txt\'.split(\'|\'),0,{})</script></html>'
                    ),
                    url='https://javclan.com/e/demo123',
                )
            raise AssertionError(f'unexpected url {url}')

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(javguru_mod, '_make_scraper', lambda: FakeScraper())
    monkeypatch.setattr(
        javguru_mod,
        'fetch_with_mirrors',
        lambda scraper, url, site_key, validate, timeout=30: (
            FakeResp(text=page_html), 'jav.guru', 'ok'),
    )

    crawler = SiteJavGuru.__new__(SiteJavGuru)
    crawler.silence = True
    crawler._url = 'https://jav.guru/1/example-title/'
    crawler.get_url_infos()
    assert crawler._m3u8url == 'https://cdn.example/master.txt'
    assert crawler._extra_headers['Referer'] == 'https://javclan.com/'
    assert crawler._extra_headers['Origin'] == 'https://javclan.com'
