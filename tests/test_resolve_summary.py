import sys
import types


def _stub(name, factory=None):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory() if factory else types.ModuleType(name)


_stub("cloudscraper")
_stub("m3u8")

from jav_downloader.web import service  # noqa: E402


class _Tier:
    def __init__(self, data):
        self.__dict__.update(data)


class FakeSite:
    def __init__(self, attrs):
        self.__dict__.update(attrs)


def test_resolve_extras_direct_mp4_has_stream_type(monkeypatch):
    import jav_downloader.sites.output_meta as output_meta

    def fake_populate(site):
        site._hls_tiers = []

    def fake_estimate(site):
        return 123, True

    monkeypatch.setattr(output_meta, "populate_hls_tiers", fake_populate)
    monkeypatch.setattr(output_meta, "estimate_output_size", fake_estimate)

    site = FakeSite({"_direct_url": "https://cdn.test/v.mp4", "_m3u8url": None})
    extras = service._site_resolve_extras(site)

    assert extras["stream_type"] == "mp4"
    assert extras["output_size_bytes"] == 123
    assert extras["output_size_exact"] is True
    assert "hls_tiers" not in extras


def test_resolve_extras_hls_includes_tiers(monkeypatch):
    import jav_downloader.sites.output_meta as output_meta

    tiers = [
        {"id": "360", "label": "360p", "height": 360, "bandwidth": 400000, "pref": "lowest", "index": 0},
        {"id": "1080", "label": "1080p", "height": 1080, "bandwidth": 3000000, "pref": "highest", "index": 1},
    ]

    def fake_populate(site):
        site._hls_tiers = tiers

    def fake_estimate(site):
        return None, False

    monkeypatch.setattr(output_meta, "populate_hls_tiers", fake_populate)
    monkeypatch.setattr(output_meta, "estimate_output_size", fake_estimate)

    site = FakeSite({"_direct_url": None, "_m3u8url": "https://cdn.test/master.m3u8"})
    extras = service._site_resolve_extras(site)

    assert extras["stream_type"] == "hls"
    assert len(extras["hls_tiers"]) == 2
    assert extras["hls_tiers"][0]["label"] == "360p"
    assert extras["hls_tiers"][1]["height"] == 1080


def test_resolve_extras_no_stream_skips_type(monkeypatch):
    import jav_downloader.sites.output_meta as output_meta

    def fake_populate(site):
        site._hls_tiers = []

    def fake_estimate(site):
        return None, False

    monkeypatch.setattr(output_meta, "populate_hls_tiers", fake_populate)
    monkeypatch.setattr(output_meta, "estimate_output_size", fake_estimate)

    site = FakeSite({"_direct_url": None, "_m3u8url": None})
    extras = service._site_resolve_extras(site)

    assert "stream_type" not in extras
    assert "hls_tiers" not in extras
