from jav_downloader.sites import encoding_decision, encoding_strategies


class DummySite:
    pass


def _site(**kwargs):
    site = DummySite()
    site._encode_codec = kwargs.get('codec', 'h264')
    site._encode_crf = kwargs.get('crf', 23)
    site._encode_max_height = kwargs.get('max_height', 480)
    site._encode_preset = kwargs.get('preset', 'veryfast')
    site._encode_threads = kwargs.get('threads', 4)
    site._audio_mute = False
    site._audio_fade = False
    site._audio_loudnorm = False
    site._audio_bitrate = 128
    site._audio_volume = 1.0
    return site


def test_strategy_for_direct_remux():
    decision = encoding_decision.EncodingDecision(
        mode=encoding_decision.MODE_DIRECT_REMUX,
        video_copy=True,
        scale_needed=False,
        reasons=('audio only',),
    )
    assert encoding_strategies.strategy_for_decision(decision) == (
        encoding_strategies.STRATEGY_DIRECT)


def test_strategy_for_software_encode():
    decision = encoding_decision.EncodingDecision(
        mode=encoding_decision.MODE_SOFTWARE_ENCODE,
        video_copy=False,
        scale_needed=True,
        reasons=('scale',),
    )
    assert encoding_strategies.strategy_for_decision(decision) == (
        encoding_strategies.STRATEGY_SOFTWARE)


def test_software_bitrate_cap_when_hardware_engine():
    site = _site(codec='h264', max_height=480)
    site._encode_engine = 'hardware'
    args = encoding_strategies.build_software_video_args(site)
    assert '-maxrate' in args
    assert '1000k' in args


def test_no_bitrate_cap_explicit_software_engine():
    site = _site(codec='h264', max_height=480)
    site._encode_engine = 'software'
    args = encoding_strategies.build_software_video_args(site)
    assert '-maxrate' not in args


def test_build_software_video_args_h264_scale():
    site = _site(codec='h264', max_height=480)
    args = encoding_strategies.build_software_video_args(site)
    assert '-vf' in args
    assert 'scale=-2:480' in args
    assert '-c:v' in args
    idx = args.index('-c:v')
    assert args[idx + 1] == 'libx264'
    assert '-crf' in args
    assert '-preset' in args


def test_build_software_video_args_hevc():
    site = _site(codec='hevc', max_height=0)
    args = encoding_strategies.build_software_video_args(site)
    idx = args.index('-c:v')
    assert args[idx + 1] == 'libx265'


def test_build_software_video_args_skip_unneeded_scale():
    site = _site(codec='h264', max_height=480)
    args = encoding_strategies.build_software_video_args(site, source_height=360)
    assert '-vf' not in args


def test_build_software_encode_cmd_structure():
    site = _site()
    cmd = encoding_strategies.build_software_encode_cmd(
        '/usr/bin/ffmpeg', site, '/in.mp4', '/out.mp4', 60.0)
    assert cmd[0] == '/usr/bin/ffmpeg'
    assert '-progress' in cmd
    assert '/in.mp4' in cmd
    assert cmd[-1] == '/out.mp4'
    assert '-movflags' in cmd


def test_build_encode_command_returns_none_for_direct():
    site = _site()
    decision = encoding_decision.EncodingDecision(
        mode=encoding_decision.MODE_SKIP,
        video_copy=True,
        scale_needed=False,
        reasons=(),
    )
    cmd = encoding_strategies.build_encode_command(
        '/usr/bin/ffmpeg', site, '/in.mp4', '/out.mp4', None, decision)
    assert cmd is None
