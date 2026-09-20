from jav_downloader.sites import encoding_decision, media_post
from jav_downloader.sites.media_probe import (
    AudioStreamInfo,
    MediaInfo,
    VideoStreamInfo,
    _parse_probe_json,
)


class DummySite:
    pass


def _site(**kwargs):
    site = DummySite()
    site._encode_enabled = kwargs.get('encode', False)
    site._encode_codec = kwargs.get('codec', 'h264')
    site._encode_max_height = kwargs.get('max_height', 0)
    site._audio_fade = kwargs.get('audio_fade', False)
    site._audio_loudnorm = kwargs.get('audio_loudnorm', False)
    site._audio_mute = kwargs.get('audio_mute', False)
    site._audio_bitrate = kwargs.get('audio_bitrate', 128)
    site._audio_volume = kwargs.get('audio_volume', 1.0)
    return site


def _media(codec='h264', height=480, width=854):
    return MediaInfo(
        path='/tmp/video.mp4',
        duration_sec=120.0,
        video=VideoStreamInfo(
            codec_name=codec,
            width=width,
            height=height,
            pix_fmt='yuv420p',
        ),
        audio=AudioStreamInfo(codec_name='aac'),
        container='mov,mp4,m4a,3gp,3g2,mj2',
    )


def test_skip_when_nothing_requested():
    site = _site(encode=False)
    decision = encoding_decision.decide_encoding(site, _media())
    assert decision.mode == encoding_decision.MODE_SKIP


def test_audio_only_direct_remux():
    site = _site(encode=False, audio_mute=True)
    decision = encoding_decision.decide_encoding(site, _media())
    assert decision.mode == encoding_decision.MODE_DIRECT_REMUX
    assert decision.video_copy is True


def test_compatible_source_skips_reencode():
    site = _site(encode=True, codec='h264', max_height=480)
    decision = encoding_decision.decide_encoding(site, _media(height=360))
    assert decision.mode == encoding_decision.MODE_SKIP
    assert 'skipping re-encode' in decision.reasons[0]


def test_compatible_source_with_audio_processing():
    site = _site(encode=True, codec='h264', max_height=480, audio_fade=True)
    decision = encoding_decision.decide_encoding(site, _media(height=360))
    assert decision.mode == encoding_decision.MODE_DIRECT_REMUX
    assert decision.video_copy is True


def test_codec_mismatch_requires_encode():
    site = _site(encode=True, codec='hevc', max_height=480)
    decision = encoding_decision.decide_encoding(site, _media(codec='h264', height=360))
    assert decision.mode == encoding_decision.MODE_SOFTWARE_ENCODE
    assert decision.needs_video_encode is True
    assert any('codec mismatch' in reason for reason in decision.reasons)


def test_downscale_requires_encode():
    site = _site(encode=True, codec='h264', max_height=480)
    decision = encoding_decision.decide_encoding(site, _media(height=720))
    assert decision.mode == encoding_decision.MODE_SOFTWARE_ENCODE
    assert decision.scale_needed is True
    assert any('resolution above max height' in reason for reason in decision.reasons)


def test_probe_unavailable_falls_back_to_encode():
    site = _site(encode=True, codec='h264', max_height=480)
    decision = encoding_decision.decide_encoding(site, None)
    assert decision.mode == encoding_decision.MODE_SOFTWARE_ENCODE
    assert 'source inspection unavailable' in decision.reasons[0]


def test_format_encoding_decision_log_skip():
    site = _site(encode=True, codec='h264', max_height=480)
    decision = encoding_decision.decide_encoding(site, _media(height=360))
    line = encoding_decision.format_encoding_decision_log(
        decision, _media(height=360), site)
    assert 'mode=direct-remux (no-op)' in line
    assert '1920' not in line
    assert '854x360' in line


def test_parse_probe_json_h264():
    payload = {
        'format': {'duration': '10.5', 'format_name': 'mov,mp4,m4a,3gp,3g2,mj2'},
        'streams': [
            {
                'codec_type': 'video',
                'codec_name': 'h264',
                'width': 1280,
                'height': 720,
                'pix_fmt': 'yuv420p',
            },
            {
                'codec_type': 'audio',
                'codec_name': 'aac',
            },
        ],
    }
    info = _parse_probe_json('/tmp/x.mp4', payload)
    assert info.video is not None
    assert info.video.normalized_codec() == 'h264'
    assert info.video.height == 720
    assert info.audio is not None
    assert info.duration_sec == 10.5


def test_video_stream_normalizes_hevc_names():
    video = VideoStreamInfo(codec_name='hev1', width=640, height=360, pix_fmt='yuv420p')
    assert video.normalized_codec() == 'hevc'


def test_direct_engine_skips_reencode():
    site = _site(encode=True, codec='hevc', max_height=480)
    site._encode_engine = 'direct'
    decision = encoding_decision.decide_encoding(site, _media(height=720, codec='h264'))
    assert decision.mode == encoding_decision.MODE_SKIP


def test_needs_media_post_unchanged():
    site = _site(encode=False)
    assert media_post.needs_media_post(site) is False
    site._encode_enabled = True
    assert media_post.needs_media_post(site) is True
