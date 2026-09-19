import sys
import types


def _stub(name, factory=None):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory() if factory else types.ModuleType(name)


_stub('cloudscraper')
_stub('m3u8')

from jav_downloader.sites.base import M3U8Crawler, _playlist_referer_origin


def test_playlist_referer_origin():
    assert _playlist_referer_origin(
        'https://gs10.turbosplayer.com/file/abc/master.m3u8',
    ) == 'https://gs10.turbosplayer.com/'


def test_segment_headers_use_media_playlist_referer():
    crawler = M3U8Crawler.__new__(M3U8Crawler)
    crawler._extra_headers = {'Referer': 'https://turbovidhls.com/'}
    crawler._segment_referer = 'https://gs10.turbosplayer.com/'
    assert crawler._segment_headers()['Referer'] == 'https://gs10.turbosplayer.com/'


def test_apply_segment_time_cut_keeps_overlapping_segments():
    crawler = M3U8Crawler.__new__(M3U8Crawler)
    crawler.silence = True
    crawler._cut_start_sec = 5.0
    crawler._cut_end_sec = 12.0
    crawler._tsList = ['a.ts', 'b.ts', 'c.ts', 'd.ts']
    crawler._segment_durations = [4.0, 4.0, 4.0, 4.0]
    crawler._segment_seq_nums = [0, 1, 2, 3]
    crawler._apply_segment_time_cut()
    assert crawler._tsList == ['b.ts', 'c.ts']
    assert crawler._segment_seq_nums == [1, 2]


def test_create_m3u8_filters_playlist_and_preserves_seq_nums(monkeypatch):
    uri_prefix = 'https://cdn.example/video'

    class FakeSegment:
        def __init__(self, uri, duration):
            self.uri = uri
            self.duration = duration

    class FakePlaylist:
        segments = [
            FakeSegment(f'{uri_prefix}/a.ts', 4.0),
            FakeSegment(f'{uri_prefix}/b.ts', 4.0),
            FakeSegment(f'{uri_prefix}/c.ts', 4.0),
            FakeSegment(f'{uri_prefix}/d.ts', 4.0),
        ]
        playlists = []
        keys = []
        media_sequence = 0

    crawler = M3U8Crawler.__new__(M3U8Crawler)
    crawler.silence = True
    crawler._m3u8url = f'{uri_prefix}/index.m3u8'
    crawler._extra_headers = {}
    crawler._cut_ranges = [(5.0, 12.0)]
    crawler._cut_start_sec = 5.0
    crawler._cut_end_sec = 12.0
    crawler._key_content = None
    crawler._key_method = None
    crawler._key_iv = None
    monkeypatch.setattr(crawler, '_load_m3u8', lambda url: FakePlaylist())

    crawler._create_m3u8()
    assert crawler._tsList == [f'{uri_prefix}/b.ts', f'{uri_prefix}/c.ts']
    assert crawler._segment_seq_nums == [1, 2]
