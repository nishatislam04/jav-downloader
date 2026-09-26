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
from jav_downloader.sites.encoding_capabilities import (
    HardwareEncoderSpec,
    resolve_hardware_encoder,
)
from jav_downloader.sites.encoding_performance import needs_video_scale
from jav_downloader.sites.media_post import (
    _append_audio_mapping,
    effective_encode_crf,
    normalize_encode_codec,
    normalize_encode_engine,
    normalize_encode_max_height,
    normalize_hardware_bitrate_kbps,
    normalize_hardware_bitrate_mode,
    normalize_hardware_gop,
    resolved_encode_preset,
    resolved_encode_threads,
    site_wants_small_file,
    wants_software_bitrate_cap,
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
    if site_wants_small_file(site):
        return STRATEGY_SOFTWARE
    engine = normalize_encode_engine(getattr(site, '_encode_engine', None))
    if engine == 'direct':
        return STRATEGY_DIRECT
    if engine == 'software':
        return STRATEGY_SOFTWARE

    target_codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    available, _, _ = resolve_hardware_encoder(target_codec)
    if engine == 'hardware':
        return STRATEGY_HARDWARE if available else STRATEGY_SOFTWARE
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
    if duration_sec and duration_sec > 0:
        return 60
    return 60


def _hardware_rate_control(site, max_height: int, duration_sec: float | None) -> tuple[int, int]:
    custom_bitrate = normalize_hardware_bitrate_kbps(
        getattr(site, '_encode_hardware_bitrate_kbps', None))
    bitrate = custom_bitrate or default_hardware_bitrate_kbps(max_height)
    custom_gop = normalize_hardware_gop(getattr(site, '_encode_hardware_gop', None))
    gop = custom_gop or default_gop_size(duration_sec)
    return bitrate, gop


def _scale_filter(max_height: int, source_height: int | None) -> list[str]:
    if not needs_video_scale(source_height, max_height):
        return []
    return ['-vf', f'scale=-2:{max_height}']


def _build_mediacodec_video_args(
        site,
        duration_sec: float | None,
        source_height: int | None) -> list[str]:
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    target_codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    _, spec, _ = resolve_hardware_encoder(target_codec, validate=False)
    encoder = spec.encoder_name if spec else (
        'hevc_mediacodec' if target_codec == 'hevc' else 'h264_mediacodec')

    bitrate, gop = _hardware_rate_control(site, max_height, duration_sec)
    mode = normalize_hardware_bitrate_mode(
        getattr(site, '_encode_hardware_bitrate_mode', None))
    if mode == 'auto':
        mode = 'vbr'

    args = _scale_filter(max_height, source_height)
    args.extend([
        '-c:v', encoder,
        '-bitrate_mode', mode,
        '-b:v', f'{bitrate}k',
        '-g', str(gop),
    ])
    return args


def _build_nvenc_video_args(
        site,
        spec: HardwareEncoderSpec,
        duration_sec: float | None,
        source_height: int | None) -> list[str]:
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    bitrate, gop = _hardware_rate_control(site, max_height, duration_sec)
    args = _scale_filter(max_height, source_height)
    args.extend([
        '-c:v', spec.encoder_name,
        '-preset', 'p4',
        '-b:v', f'{bitrate}k',
        '-g', str(gop),
    ])
    return args


def _build_qsv_video_args(
        site,
        spec: HardwareEncoderSpec,
        duration_sec: float | None,
        source_height: int | None) -> list[str]:
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    bitrate, gop = _hardware_rate_control(site, max_height, duration_sec)
    args = _scale_filter(max_height, source_height)
    args.extend([
        '-c:v', spec.encoder_name,
        '-b:v', f'{bitrate}k',
        '-g', str(gop),
    ])
    return args


def _build_videotoolbox_video_args(
        site,
        spec: HardwareEncoderSpec,
        duration_sec: float | None,
        source_height: int | None) -> list[str]:
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    bitrate, gop = _hardware_rate_control(site, max_height, duration_sec)
    args = _scale_filter(max_height, source_height)
    args.extend([
        '-c:v', spec.encoder_name,
        '-b:v', f'{bitrate}k',
        '-g', str(gop),
    ])
    return args


def _build_vaapi_video_args(
        site,
        spec: HardwareEncoderSpec,
        duration_sec: float | None,
        source_height: int | None) -> list[str]:
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    bitrate, gop = _hardware_rate_control(site, max_height, duration_sec)
    if needs_video_scale(source_height, max_height):
        vf = f'format=nv12,hwupload,scale_vaapi=w=-2:h={max_height}'
    else:
        vf = 'format=nv12,hwupload'
    return [
        '-vf', vf,
        '-c:v', spec.encoder_name,
        '-b:v', f'{bitrate}k',
        '-g', str(gop),
    ]


def build_hardware_video_args(
        site,
        duration_sec: float | None = None,
        source_height: int | None = None) -> list[str]:
    target_codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    ok, spec, reason = resolve_hardware_encoder(target_codec, validate=False)
    if not ok or spec is None:
        raise ValueError(reason or f'no hardware encoder for {target_codec}')

    if spec.backend_id == 'mediacodec':
        return _build_mediacodec_video_args(site, duration_sec, source_height)
    if spec.backend_id == 'nvenc':
        return _build_nvenc_video_args(site, spec, duration_sec, source_height)
    if spec.backend_id == 'qsv':
        return _build_qsv_video_args(site, spec, duration_sec, source_height)
    if spec.backend_id == 'vaapi':
        return _build_vaapi_video_args(site, spec, duration_sec, source_height)
    if spec.backend_id == 'videotoolbox':
        return _build_videotoolbox_video_args(site, spec, duration_sec, source_height)
    raise ValueError(f'unsupported hardware backend {spec.backend_id}')


def _hardware_input_prefix(spec: HardwareEncoderSpec) -> list[str]:
    if spec.backend_id == 'vaapi' and spec.vaapi_device:
        return [
            '-init_hw_device', f'vaapi=va:{spec.vaapi_device}',
            '-filter_hw_device', 'va',
        ]
    return []


def build_hardware_encode_cmd(
        ffmpeg: str,
        site,
        src_path: str,
        dst_path: str,
        duration_sec: float | None,
        source_height: int | None = None) -> list[str]:
    target_codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    _, spec, _ = resolve_hardware_encoder(target_codec, validate=False)
    cmd = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
           '-nostats', '-progress', 'pipe:1']
    if spec:
        cmd.extend(_hardware_input_prefix(spec))
    cmd.extend(['-i', src_path])
    cmd.extend(build_hardware_video_args(site, duration_sec, source_height))
    _append_audio_mapping(cmd, site, duration_sec, video_copy=False)
    cmd.extend(['-movflags', '+faststart', dst_path])
    return cmd


def _software_vbr_cap_args(site) -> list[str]:
    if not wants_software_bitrate_cap(site):
        return []
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    custom = normalize_hardware_bitrate_kbps(
        getattr(site, '_encode_hardware_bitrate_kbps', None))
    bitrate = custom or default_hardware_bitrate_kbps(max_height)
    if bitrate <= 0:
        return []
    return ['-maxrate', f'{bitrate}k', '-bufsize', f'{bitrate * 2}k']


def build_software_video_args(
        site,
        source_height: int | None = None) -> list[str]:
    """Return ffmpeg video encoder arguments for software x264/x265."""
    preset = resolved_encode_preset(site)
    codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    crf = effective_encode_crf(site)
    max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))

    args = _scale_filter(max_height, source_height)
    if codec == 'hevc':
        args.extend(['-c:v', 'libx265', '-crf', str(crf), '-preset', preset])
    else:
        args.extend([
            '-c:v', 'libx264', '-crf', str(crf), '-preset', preset,
            '-g', '60', '-keyint_min', '60', '-sc_threshold', '0',
        ])
    args.extend(_software_vbr_cap_args(site))
    return args


def build_software_encode_cmd(
        ffmpeg: str,
        site,
        src_path: str,
        dst_path: str,
        duration_sec: float | None,
        source_height: int | None = None) -> list[str]:
    """Full ffmpeg command for software re-encode (existing behavior)."""
    threads = resolved_encode_threads(site)
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-nostats', '-progress', 'pipe:1',
        '-threads', str(threads),
        '-i', src_path,
    ]
    cmd.extend(build_software_video_args(site, source_height))
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
        strategy: str | None = None,
        source_height: int | None = None) -> list[str] | None:
    """Build ffmpeg command for the selected encoding strategy."""
    chosen = strategy or strategy_for_decision(decision, site)
    if chosen == STRATEGY_DIRECT:
        return None
    if chosen == STRATEGY_HARDWARE:
        return build_hardware_encode_cmd(
            ffmpeg, site, src_path, dst_path, duration_sec, source_height)
    return build_software_encode_cmd(
        ffmpeg, site, src_path, dst_path, duration_sec, source_height)


def encode_strategy_label(strategy: str, site) -> str:
    if strategy == STRATEGY_HARDWARE:
        codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
        max_height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
        bitrate = default_hardware_bitrate_kbps(max_height)
        height_label = f'{max_height}p' if max_height > 0 else 'original'
        codec_label = 'H.265' if codec == 'hevc' else 'H.264'
        return f'Hardware {codec_label} · {height_label} · {bitrate}k'
    preset = resolved_encode_preset(site)
    codec = normalize_encode_codec(getattr(site, '_encode_codec', None))
    crf = effective_encode_crf(site)
    height = normalize_encode_max_height(getattr(site, '_encode_max_height', None))
    threads = resolved_encode_threads(site)
    height_label = f'{height}p' if height > 0 else 'original'
    codec_label = 'H.265' if codec == 'hevc' else 'H.264'
    cap = _software_vbr_cap_args(site)
    cap_label = ''
    if cap:
        cap_label = f' · cap {cap[1]}'
    return (
        f'{codec_label} CRF {crf} · {height_label} · {preset} · '
        f'{threads} thread(s){cap_label}')
