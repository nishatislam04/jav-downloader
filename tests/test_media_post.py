import os

from jav_downloader.sites import media_post


class DummySite:
    pass


def test_normalize_encode_crf_clamps():
    assert media_post.normalize_encode_crf(10) == 18
    assert media_post.normalize_encode_crf(99) == 28
    assert media_post.normalize_encode_crf('24') == 24


def test_encode_tag_hevc_with_height():
    site = DummySite()
    site._encode_codec = 'hevc'
    site._encode_crf = 22
    site._encode_max_height = 720
    assert media_post.encode_tag(site) == 'h265-crf22-720p'


def test_encode_destination_keep_both():
    site = DummySite()
    site._encode_output_mode = 'keep_both'
    site._encode_codec = 'h264'
    site._encode_crf = 23
    site._encode_max_height = 0
    path, mode = media_post._encode_destination_path('/tmp/video.mp4', site)
    assert mode == 'keep_both'
    assert path == '/tmp/video [h264-crf23].mp4'


def test_finalize_processed_output_keep_both(tmp_path, monkeypatch):
    site = DummySite()
    site._encode_output_mode = "keep_both"
    site._encode_codec = "h264"
    site._encode_crf = 28
    site._encode_max_height = 480
    site._audio_mute = True
    src = tmp_path / "video.mp4"
    src.write_bytes(b"original")
    captured = {}

    def fake_audio(site, src_path, duration_sec=None, *, dst_path=None):
        captured["dst"] = dst_path
        with open(dst_path, "wb") as handle:
            handle.write(b"processed")

    monkeypatch.setattr(media_post, "post_process_audio", fake_audio)
    out = media_post.finalize_processed_output(site, str(src))
    assert src.read_bytes() == b"original"
    assert "[h264-crf28-480p]" in out
    assert captured["dst"] == out


def test_emit_encode_progress_uses_time_unit():
    site = DummySite()
    captured = []

    def _cb(downloaded, total, speed, unit):
        captured.append((downloaded, total, speed, unit))

    site._progress_callback = _cb
    media_post._emit_encode_progress(site, '/missing.mp4', 90.0, 600.0, 50_000_000)
    assert captured
    downloaded, total, _speed, unit = captured[-1]
    assert unit == 'time'
    assert total == 600_000
    assert downloaded == 90_000


def test_apply_encode_options_sets_flags():
    site = DummySite()
    media_post.apply_encode_options(
        site,
        encode=True,
        encode_codec='hevc',
        encode_crf=21,
        encode_max_height=1080,
        encode_output_mode='suffix',
        encode_preset='fast',
        encode_threads=4,
    )
    assert site._encode_enabled is True
    assert site._encode_codec == 'hevc'
    assert site._encode_crf == 21
    assert site._encode_max_height == 1080
    assert site._encode_output_mode == 'suffix'
    assert site._encode_preset == 'fast'
    assert site._encode_threads == 4


def test_needs_media_post():
    site = DummySite()
    site._encode_enabled = False
    site._audio_fade = False
    site._audio_loudnorm = False
    site._audio_mute = False
    site._audio_bitrate = 128
    site._audio_volume = 1.0
    assert media_post.needs_media_post(site) is False
    site._encode_enabled = True
    assert media_post.needs_media_post(site) is True
    site._encode_enabled = False
    site._audio_mute = True
    assert media_post.needs_media_post(site) is True


def test_build_af_filter_volume_before_fade():
    site = DummySite()
    site._audio_mute = False
    site._audio_volume = 2.0
    site._audio_fade = True
    site._audio_loudnorm = False
    af = media_post.build_af_filter(site, 10.0)
    assert af.startswith('volume=2')
    assert 'afade' in af


def test_normalize_audio_bitrate():
    assert media_post.normalize_audio_bitrate(96) == 96
    assert media_post.normalize_audio_bitrate(999) == 128


def test_apply_audio_options():
    site = DummySite()
    media_post.apply_audio_options(
        site,
        audio_fade=True,
        audio_loudnorm=False,
        audio_mute=True,
        audio_bitrate=192,
        audio_volume=2.5,
    )
    assert site._audio_mute is True
    assert site._audio_bitrate == 192
    assert site._audio_volume == 2.5


def test_resolved_encode_threads_auto(monkeypatch):
    site = DummySite()
    site._encode_threads = 0
    monkeypatch.setattr(os, 'cpu_count', lambda: 8)
    assert media_post.resolved_encode_threads(site) == 8
