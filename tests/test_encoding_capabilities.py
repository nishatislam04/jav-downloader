from jav_downloader.sites import encoding_capabilities, encoding_strategies


def test_parse_ffmpeg_encoders():
    text = """
 Encoders:
 V..... libx264              libx264 H.264
 V..... h264_mediacodec      H.264 Android MediaCodec
 V..... hevc_mediacodec      HEVC Android MediaCodec
"""
    names = encoding_capabilities._parse_ffmpeg_encoders(text)
    assert 'libx264' in names
    assert 'h264_mediacodec' in names
    assert 'hevc_mediacodec' in names


def test_mediacodec_encoder_name():
    assert encoding_capabilities.mediacodec_encoder_name('h264') == 'h264_mediacodec'
    assert encoding_capabilities.mediacodec_encoder_name('hevc') == 'hevc_mediacodec'


def test_hardware_unavailable_on_non_android(monkeypatch):
    monkeypatch.setattr(encoding_capabilities, 'is_android_like', lambda: False)
    encoding_capabilities.clear_capability_cache()
    ok, name, reason = encoding_capabilities.hardware_encoder_available('h264')
    assert ok is False
    assert reason == 'not Android'


def test_resolve_encode_strategy_forces_software(monkeypatch):
    class Site:
        _encode_engine = 'software'
        _encode_codec = 'h264'

    monkeypatch.setattr(encoding_capabilities, 'is_android_like', lambda: True)
    assert encoding_strategies.resolve_encode_strategy(Site()) == (
        encoding_strategies.STRATEGY_SOFTWARE)


def test_build_hardware_video_args(monkeypatch):
    class Site:
        _encode_codec = 'h264'
        _encode_max_height = 480

    args = encoding_strategies.build_hardware_video_args(Site(), 30.0)
    assert '-c:v' in args
    idx = args.index('-c:v')
    assert args[idx + 1] == 'h264_mediacodec'
    assert '-bitrate_mode' in args
    assert '-b:v' in args
    assert '-g' in args
    gidx = args.index('-g')
    assert args[gidx + 1] == '60'


def test_default_hardware_bitrate_scales_with_height():
    assert encoding_strategies.default_hardware_bitrate_kbps(480) == 1000
    assert encoding_strategies.default_hardware_bitrate_kbps(720) == 2500
    assert encoding_strategies.default_hardware_bitrate_kbps(1080) == 5000
