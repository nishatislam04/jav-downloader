#!/usr/bin/env python
# coding: utf-8
"""FFmpeg command builders for post-download encoding strategies."""

from __future__ import annotations

from jav_downloader.sites.encoding_decision import (
    MODE_DIRECT_REMUX,
    MODE_SKIP,
    MODE_SOFTWARE_ENCODE,
    EncodingDecision,
)
from jav_downloader.sites.media_post import (
    _append_audio_mapping,
    normalize_encode_codec,
    normalize_encode_crf,
    normalize_encode_engine,
    normalize_encode_max_height,
    resolved_encode_preset,
    resolved_encode_threads,
)

STRATEGY_DIRECT = 'direct_remux'
STRATEGY_SOFTWARE = 'software_ffmpeg'
STRATEGY_HARDWARE = 'hardware_ffmpeg'


def strategy_for_decision(decision: EncodingDecision, site=None) -> str:
    if decision.mode in (MODE_SKIP, MODE_DIRECT_REMUX):
        return STRATEGY_DIRECT
    if decision.mode != MODE_SOFTWARE_ENCODE:
        return STRATEGY_SOFTWARE
    return resolve_encode_strategy(site) if site is not None else STRATEGY_SOFTWARE


def resolve_encode_strategy(site) -> str:
    """Pick hardware or software encoder from site engine preference."""
    engine = normalize_encode_engine(getattr(site, '_encode_engine', None))
    if engine == 'direct':
        return STRATEGY_DIRECT
    if engine == 'software':
        return STRATEGY_SOFTWARE

    from jav_downloader.sites.encoding_capabilities import hardware_encoder_available

    target_codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    available, _, _ = hardware_encoder_available(target_codec)
    if engine == 'hardware':
        return STRATEGY_HARDWARE if available else STRATEGY_SOFTWARE
    # auto
    return STRATEGY_HARDWARE if available else STRATEGY_SOFTWARE


def default_hardware_bitrate_kbps(max_height: int) -> int:
    if max_height <= 0:
        return 2500
    if max_height <= 480:
        return 1000
    if max_height <= 720:
        return 2500
    return 5000


def default_gop_size(duration_sec: float | None) -> int:
    # ~2 s keyframe interval at 30 fps; explicit GOP avoids MediaCodec warnings.
    if duration_sec and duration_sec > 0:
        return 60
    return 60


def build_hardware_video_args(site, duration_sec: float | None = None) -> list[str]:
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    target_codec = normalize_encode_codec(getattr(site, '_encode_codec', None))

    from jav_downloader.sites.encoding_capabilities import mediacodec_encoder_name

    encoder = mediacodec_encoder_name(target_codec)
    if not encoder:
        raise ValueError(f'no MediaCodec encoder for {target_codec}')

    from jav_downloader.sites.media_post import (
        normalize_hardware_bitrate_kbps,
        normalize_hardware_bitrate_mode,
        normalize_hardware_gop,
    )

    custom_bitrate = normalize_hardware_bitrate_kbps(
        getattr(site, '_encode_hardware_bitrate_kbps', None))
    bitrate = custom_bitrate or default_hardware_bitrate_kbps(max_height)
    custom_gop = normalize_hardware_gop(getattr(site, '_encode_hardware_gop', None))
    gop = custom_gop or default_gop_size(duration_sec)
    mode = normalize_hardware_bitrate_mode(
        getattr(site, '_encode_hardware_bitrate_mode', None))
    if mode == 'auto':
        mode = 'vbr'

    args: list[str] = []
    if max_height > 0:
        args.extend(['-vf', f'scale=-2:{max_height}'])
    args.extend([
        '-c:v', encoder,
        '-bitrate_mode', mode,
        '-b:v', f'{bitrate}k',
        '-g', str(gop),
    ])
    return args


def build_hardware_encode_cmd(
        ffmpeg: str,
        site,
        src_path: str,
        dst_path: str,
        duration_sec: float | None) -> list[str]:
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-nostats', '-progress', 'pipe:1',
        '-i', src_path,
    ]
    cmd.extend(build_hardware_video_args(site, duration_sec))
    _append_audio_mapping(cmd, site, duration_sec, video_copy=False)
    cmd.extend(['-movflags', '+faststart', dst_path])
    return cmd


def build_software_video_args(site) -> list[str]:
    """Return ffmpeg video encoder arguments for software x264/x265."""
    preset = resolved_encode_preset(site)
    codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    crf = normalize_encode_crf(getattr(site, '_encode_crf', None))
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))

    args: list[str] = []
    if max_height > 0:
        args.extend(['-vf', f'scale=-2:{max_height}'])
    if codec == 'hevc':
        args.extend(['-c:v', 'libx265', '-crf', str(crf), '-preset', preset])
    else:
        args.extend(['-c:v', 'libx264', '-crf', str(crf), '-preset', preset])
    return args


def build_software_encode_cmd(
        ffmpeg: str,
        site,
        src_path: str,
        dst_path: str,
        duration_sec: float | None) -> list[str]:
    """Full ffmpeg command for software re-encode (existing behavior)."""
    threads = resolved_encode_threads(site)
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-nostats', '-progress', 'pipe:1',
        '-threads', str(threads),
        '-i', src_path,
    ]
    cmd.extend(build_software_video_args(site))
    _append_audio_mapping(cmd, site, duration_sec, video_copy=False)
    cmd.extend(['-movflags', '+faststart', dst_path])
    return cmd


def build_encode_command(
        ffmpeg: str,
        site,
        src_path: str,
        dst_path: str,
        duration_sec: float | None,
        decision: EncodingDecision,
        *,
        strategy: str | None = None) -> list[str] | None:
    """Build ffmpeg command for the selected encoding strategy."""
    chosen = strategy or strategy_for_decision(decision, site)
    if chosen == STRATEGY_DIRECT:
        return None
    if chosen == STRATEGY_HARDWARE:
        return build_hardware_encode_cmd(
            ffmpeg, site, src_path, dst_path, duration_sec)
    return build_software_encode_cmd(
        ffmpeg, site, src_path, dst_path, duration_sec)


def encode_strategy_label(strategy: str, site) -> str:
    if strategy == STRATEGY_HARDWARE:
        from jav_downloader.sites.encoding_capabilities import mediacodec_encoder_name

        codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
        encoder = mediacodec_encoder_name(codec) or 'mediacodec'
        max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
        bitrate = default_hardware_bitrate_kbps(max_height)
        height_label = f'{max_height}p' if max_height > 0 else 'original'
        return f'{encoder} VBR {bitrate}k · {height_label} · gop {default_gop_size(None)}'
    preset = resolved_encode_preset(site)
    codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    crf = normalize_encode_crf(getattr(site, '_encode_crf', None))
    height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    threads = resolved_encode_threads(site)
    height_label = f'{height}p' if height > 0 else 'original'
    codec_label = 'H.265' if codec == 'hevc' else 'H.264'
    return f'{codec_label} CRF {crf} · {height_label} · {preset} · {threads} thread(s)'
