from jav_downloader.sites.encoding_performance import (
    cached_probe_media,
    ffmpeg_work_session,
    needs_video_scale,
)


class DummySite:
    pass


def test_needs_video_scale():
    assert needs_video_scale(720, 480) is True
    assert needs_video_scale(360, 480) is False
    assert needs_video_scale(None, 480) is True
    assert needs_video_scale(720, 0) is False


def test_cached_probe_media_reuses_site_cache(monkeypatch):
    site = DummySite()
    calls = {'count': 0}

    class Info:
        pass

    def fake_probe(path):
        calls['count'] += 1
        return Info()

    monkeypatch.setattr(
        'jav_downloader.sites.media_probe.probe_media', fake_probe)

    first = cached_probe_media(site, '/tmp/a.mp4')
    second = cached_probe_media(site, '/tmp/a.mp4')
    assert first is second
    assert calls['count'] == 1


def test_ffmpeg_work_session_noop_off_android(monkeypatch):
    monkeypatch.setattr(
        'jav_downloader.sites.encoding_performance.is_android_like',
        lambda: False,
    )
    with ffmpeg_work_session():
        pass
