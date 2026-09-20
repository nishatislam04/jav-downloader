from types import SimpleNamespace

from jav_downloader.sites import output_meta as meta_mod


def test_effective_output_duration_sec_sums_cuts():
    site = SimpleNamespace(
        _cut_ranges=[(10.0, 40.0), (100.0, 130.0)],
        _duration_sec=200.0,
    )
    assert meta_mod.effective_output_duration_sec(site) == 60.0


def test_estimate_output_size_scales_direct_mp4_with_cuts(monkeypatch):
    site = SimpleNamespace(
        _direct_url='https://cdn.example/video.mp4',
        _direct_referer='https://example.test/',
        _extra_headers={},
        _duration_sec=100.0,
        _cut_ranges=[(0.0, 50.0)],
        _m3u8url=None,
    )
    monkeypatch.setattr(
        'jav_downloader.sites.direct_mp4.probe_source_length',
        lambda *args, **kwargs: 100_000_000,
    )
    size, exact = meta_mod.estimate_output_size(site)
    assert exact is True
    assert size == 50_000_000


def test_estimate_output_size_hls_uses_bandwidth(monkeypatch):
    site = SimpleNamespace(
        _direct_url=None,
        _m3u8url='https://cdn.example/master.m3u8',
        _duration_sec=100.0,
        _cut_ranges=[],
        _selected_variant_bandwidth=8_000_000,
        _selected_variant_height=720,
    )
    monkeypatch.setattr(meta_mod, '_estimate_hls_size_from_segments', lambda _site: None)
    size, exact = meta_mod.estimate_output_size(site)
    assert exact is False
    assert size == 100_000_000


def test_estimate_output_size_hls_hides_implausible_bandwidth(monkeypatch):
    site = SimpleNamespace(
        _direct_url=None,
        _m3u8url='https://cdn.example/stream.m3u8',
        _duration_sec=100.0,
        _cut_ranges=[(0.0, 300.0)],
        _selected_variant_bandwidth=31_000,
        _selected_variant_height=480,
    )
    monkeypatch.setattr(meta_mod, '_estimate_hls_size_from_segments', lambda _site: None)
    size, exact = meta_mod.estimate_output_size(site)
    assert size is None
    assert exact is False


def test_estimate_output_size_hls_prefers_segment_probe(monkeypatch):
    site = SimpleNamespace(
        _direct_url=None,
        _m3u8url='https://cdn.example/stream.m3u8',
        _duration_sec=3600.0,
        _cut_ranges=[(0.0, 300.0)],
        _selected_variant_bandwidth=31_000,
        _selected_variant_height=480,
        _hls_media_duration_sec=3600.0,
    )
    monkeypatch.setattr(meta_mod, '_estimate_hls_size_from_segments', lambda _site: 18_000_000)
    size, exact = meta_mod.estimate_output_size(site)
    assert exact is False
    assert size == 18_000_000


def test_media_playlist_duration_sec_sums_segments():
    segments = [
        SimpleNamespace(duration=6.0),
        SimpleNamespace(duration=6.0),
        SimpleNamespace(duration=4.5),
    ]
    m3u8 = SimpleNamespace(segments=segments)
    assert meta_mod._media_playlist_duration_sec(m3u8) == 16.5
