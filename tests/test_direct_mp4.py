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

from uav_downloader.sites.base import (
    M3U8Crawler,
    parse_time_seconds,
    validate_cut_against_duration,
)
from uav_downloader.sites.direct_mp4 import (
    _cut_progress_total,
    _emit_cut_progress,
    _parse_ffmpeg_out_time_sec,
    content_range,
    estimate_cut_total_bytes,
)


def test_validate_cut_against_duration_rejects_end_beyond_video():
    with pytest.raises(ValueError, match='End time exceeds video length'):
        validate_cut_against_duration(0, 4000, 137)


def test_parse_time_seconds_accepts_seconds_and_clock():
    assert parse_time_seconds('90') == 90.0
    assert parse_time_seconds('1:30') == 90.0
    assert parse_time_seconds('01:02:03') == 3723.0


def test_parse_time_seconds_rejects_invalid_range():
    with pytest.raises(ValueError):
        parse_time_seconds('bad')


def test_content_range_parses_bytes_header():
    assert content_range('bytes 100-199/500') == (100, 199, 500)


def test_parse_ffmpeg_out_time_sec_accepts_us_ms_and_clock():
    assert _parse_ffmpeg_out_time_sec('out_time_us=2500000') == 2.5
    assert _parse_ffmpeg_out_time_sec('out_time_ms=1500') == 1.5
    assert _parse_ffmpeg_out_time_sec('out_time=00:01:30.000000') == 90.0


def test_emit_cut_progress_uses_ffmpeg_time_before_file_bytes():
    calls = []
    site = M3U8Crawler.__new__(M3U8Crawler)
    site._progress_callback = lambda d, t, s: calls.append((d, t, s))
    _emit_cut_progress(site, 0, 0.0, 30.0, 60.0, 0)
    assert calls == [(500, 1000, 0.0)]


def test_cut_progress_total_extrapolates_from_ffmpeg_time():
    total = _cut_progress_total(0, 50_000_000, 30.0, 60.0)
    assert total == 100_000_000


def test_estimate_cut_total_bytes_scales_by_duration(monkeypatch):
    site = M3U8Crawler.__new__(M3U8Crawler)
    site._direct_url = 'https://cdn.example/video.mp4'
    site._duration_sec = 100.0
    monkeypatch.setattr(
        'uav_downloader.sites.direct_mp4.probe_source_length',
        lambda url, referer, extra_headers=None, session=None: 100_000_000,
    )
    assert estimate_cut_total_bytes(site, 0, 50, 50, 'https://example.test/') == 50_000_000


def test_cut_output_suffix_appended_to_filename():
    crawler = M3U8Crawler.__new__(M3U8Crawler)
    crawler._targetName = 'Example Title'
    crawler._dest_folder = '/tmp/out'
    crawler._cut_start_sec = 90.0
    crawler._cut_end_sec = 300.0
    assert crawler._get_video_savename().endswith('Example Title [0130-0500].mp4')
