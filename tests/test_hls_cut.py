import sys
import types


def _stub(name, factory=None):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory() if factory else types.ModuleType(name)


_stub('cloudscraper')
_stub('m3u8')

from jav_downloader.sites.base import M3U8Crawler


def test_apply_segment_time_cut_keeps_overlapping_segments():
    crawler = M3U8Crawler.__new__(M3U8Crawler)
    crawler.silence = True
    crawler._cut_start_sec = 5.0
    crawler._cut_end_sec = 12.0
    crawler._tsList = ['a.ts', 'b.ts', 'c.ts', 'd.ts']
    crawler._segment_durations = [4.0, 4.0, 4.0, 4.0]
    crawler._apply_segment_time_cut()
    assert crawler._tsList == ['b.ts', 'c.ts']
