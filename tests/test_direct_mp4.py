import sys
import types

import pytest


def _stub(name, factory=None):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory() if factory else types.ModuleType(name)


_stub('cloudscraper')
_stub('m3u8')

from uav_downloader.sites.base import M3U8Crawler, parse_time_seconds
from uav_downloader.sites.direct_mp4 import content_range


def test_parse_time_seconds_accepts_seconds_and_clock():
    assert parse_time_seconds('90') == 90.0
    assert parse_time_seconds('1:30') == 90.0
    assert parse_time_seconds('01:02:03') == 3723.0


def test_parse_time_seconds_rejects_invalid_range():
    with pytest.raises(ValueError):
        parse_time_seconds('bad')


def test_content_range_parses_bytes_header():
    assert content_range('bytes 100-199/500') == (100, 199, 500)


def test_cut_output_suffix_appended_to_filename():
    crawler = M3U8Crawler.__new__(M3U8Crawler)
    crawler._targetName = 'Example Title'
    crawler._dest_folder = '/tmp/out'
    crawler._cut_start_sec = 90.0
    crawler._cut_end_sec = 300.0
    assert crawler._get_video_savename().endswith('Example Title [0130-0500].mp4')
