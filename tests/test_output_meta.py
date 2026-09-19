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
    )
    size, exact = meta_mod.estimate_output_size(site)
    assert exact is False
    assert size == 100_000_000
