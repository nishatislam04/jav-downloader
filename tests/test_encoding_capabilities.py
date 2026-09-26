from jav_downloader.sites import encoding_capabilities, encoding_strategies
from jav_downloader.sites.encoding_capabilities import HardwareEncoderSpec


def test_parse_ffmpeg_encoders():
    text = """
 Encoders:
 V..... libx264              libx264 H.264
 V..... h264_mediacodec      H.264 Android MediaCodec
 V..... hevc_mediacodec      HEVC Android MediaCodec
 V..... h264_nvenc           NVIDIA NVENC H.264
"""
    names = encoding_capabilities._parse_ffmpeg_encoders(text)
    assert 'libx264' in names
    assert 'h264_mediacodec' in names
    assert 'h264_nvenc' in names


def test_mediacodec_encoder_name():
    assert encoding_capabilities.mediacodec_encoder_name('h264') == 'h264_mediacodec'
    assert encoding_capabilities.mediacodec_encoder_name('hevc') == 'hevc_mediacodec'


def test_hardware_unavailable_when_no_encoders_listed(monkeypatch):
    monkeypatch.setattr(
        encoding_capabilities, 'list_ffmpeg_encoders', lambda *a, **k: frozenset())
    monkeypatch.setattr(encoding_capabilities, 'is_android_like', lambda: False)
    encoding_capabilities.clear_capability_cache()
    ok, name, reason = encoding_capabilities.hardware_encoder_available('h264')
    assert ok is False
    assert name is None
    assert 'no hardware encoder listed' in (reason or '')


def test_mediacodec_trusted_when_listed_on_android(monkeypatch):
    monkeypatch.setattr(encoding_capabilities, 'is_android_like', lambda: True)
    monkeypatch.setattr(
        encoding_capabilities,
        'list_ffmpeg_encoders',
        lambda *a, **k: frozenset({'h264_mediacodec', 'hevc_mediacodec'}),
    )
    monkeypatch.setattr(
        encoding_capabilities,
        '_probe_mediacodec_encoder',
        lambda *a, **k: False,
    )
    encoding_capabilities.clear_capability_cache()

    ok, spec, reason = encoding_capabilities.resolve_hardware_encoder(
        'h264', validate=True)
    assert ok is True
    assert spec is not None
    assert spec.encoder_name == 'h264_mediacodec'
    assert reason is None
    assert encoding_capabilities.validation_probe_passed(spec) is False


def test_resolve_desktop_nvenc(monkeypatch):
    monkeypatch.setattr(encoding_capabilities, 'is_android_like', lambda: False)
    monkeypatch.setattr(
        encoding_capabilities,
        'list_ffmpeg_encoders',
        lambda *a, **k: frozenset({'h264_nvenc', 'hevc_nvenc'}),
    )
    monkeypatch.setattr(
        encoding_capabilities,
        'validate_hardware_encoder',
        lambda spec, ffmpeg=None, refresh=False: spec.backend_id == 'nvenc',
    )
    encoding_capabilities.clear_capability_cache()

    ok, spec, reason = encoding_capabilities.resolve_hardware_encoder(
        'h264', validate=True)
    assert ok is True
    assert spec is not None
    assert spec.backend_id == 'nvenc'
    assert spec.encoder_name == 'h264_nvenc'
    assert reason is None


def test_resolve_encode_strategy_forces_software(monkeypatch):
    class Site:
        _encode_engine = 'software'
        _encode_codec = 'h264'

    monkeypatch.setattr(encoding_capabilities, 'is_android_like', lambda: True)
    assert encoding_strategies.resolve_encode_strategy(Site()) == (
        encoding_strategies.STRATEGY_SOFTWARE)


def test_build_hardware_video_args_mediacodec(monkeypatch):
    monkeypatch.setattr(encoding_capabilities, 'is_android_like', lambda: True)
    monkeypatch.setattr(
        encoding_strategies,
        'resolve_hardware_encoder',
        lambda codec, ffmpeg=None, validate=True: (
            True,
            HardwareEncoderSpec('mediacodec', 'h264_mediacodec', 'android'),
            None,
        ),
    )

    class Site:
        _encode_codec = 'h264'
        _encode_max_height = 480

    args = encoding_strategies.build_hardware_video_args(Site(), 30.0, 360)
    assert '-c:v' in args
    idx = args.index('-c:v')
    assert args[idx + 1] == 'h264_mediacodec'
    assert 'scale=-2:480' not in ' '.join(args)


def test_build_hardware_video_args_nvenc(monkeypatch):
    monkeypatch.setattr(
        encoding_strategies,
        'resolve_hardware_encoder',
        lambda codec, ffmpeg=None, validate=True: (
            True,
            HardwareEncoderSpec('nvenc', 'h264_nvenc', 'desktop'),
            None,
        ),
    )

    class Site:
        _encode_codec = 'h264'
        _encode_max_height = 480

    args = encoding_strategies.build_hardware_video_args(Site(), 30.0, 720)
    idx = args.index('-c:v')
    assert args[idx + 1] == 'h264_nvenc'
    assert '-preset' in args
    assert 'scale=-2:480' in ' '.join(args)


def test_build_vaapi_video_args_skips_scale_when_unneeded(monkeypatch):
    monkeypatch.setattr(
        encoding_strategies,
        'resolve_hardware_encoder',
        lambda codec, ffmpeg=None, validate=True: (
            True,
            HardwareEncoderSpec(
                'vaapi', 'h264_vaapi', 'desktop', vaapi_device='/dev/dri/renderD128'),
            None,
        ),
    )

    class Site:
        _encode_codec = 'h264'
        _encode_max_height = 480

    args = encoding_strategies.build_hardware_video_args(Site(), 30.0, 360)
    vf = args[args.index('-vf') + 1]
    assert 'scale_vaapi' not in vf
    assert 'hwupload' in vf


def test_default_hardware_bitrate_scales_with_height():
    assert encoding_strategies.default_hardware_bitrate_kbps(480) == 1000
    assert encoding_strategies.default_hardware_bitrate_kbps(720) == 2500
    assert encoding_strategies.default_hardware_bitrate_kbps(1080) == 5000
