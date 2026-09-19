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
    assert media_post.needs_media_post(site) is False
    site._encode_enabled = True
    assert media_post.needs_media_post(site) is True


def test_resolved_encode_threads_auto(monkeypatch):
    site = DummySite()
    site._encode_threads = 0
    monkeypatch.setattr(os, 'cpu_count', lambda: 8)
    assert media_post.resolved_encode_threads(site) == 8
