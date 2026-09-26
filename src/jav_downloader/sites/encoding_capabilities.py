#!/usr/bin/env python
# coding: utf-8
"""Runtime detection of FFmpeg hardware encoder capabilities."""

from __future__ import annotations

import os
import platform
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass

from jav_downloader.sites.base import _no_window_kwargs, locate_ffmpeg

_CACHE_LOCK = threading.Lock()
_ENCODER_LISTING: frozenset[str] | None = None
# (usable_for_encode, startup_probe_passed)
_VALIDATED: dict[tuple[str, str], tuple[bool, bool]] = {}
_VAAPI_DEVICE: str | None = None
_VAAPI_DEVICE_CHECKED = False

_MEDIACODEC_ENCODERS = {'h264': 'h264_mediacodec', 'hevc': 'hevc_mediacodec'}

# Desktop backend priority for auto selection (first validated wins).
_DESKTOP_BACKENDS = (
    {
        'id': 'nvenc',
        'encoders': {'h264': 'h264_nvenc', 'hevc': 'hevc_nvenc'},
    },
    {
        'id': 'qsv',
        'encoders': {'h264': 'h264_qsv', 'hevc': 'hevc_qsv'},
    },
    {
        'id': 'vaapi',
        'encoders': {'h264': 'h264_vaapi', 'hevc': 'hevc_vaapi'},
    },
)

if platform.system().lower() == 'darwin':
    _DESKTOP_BACKENDS = _DESKTOP_BACKENDS + (
        {
            'id': 'videotoolbox',
            'encoders': {'h264': 'h264_videotoolbox', 'hevc': 'hevc_videotoolbox'},
        },
    )


@dataclass(frozen=True)
class HardwareEncoderSpec:
    backend_id: str
    encoder_name: str
    platform: str
    vaapi_device: str | None = None


def is_android_like() -> bool:
    if os.environ.get('TERMUX_VERSION'):
        return True
    if platform.system().lower() != 'linux':
        return False
    return os.path.isfile('/system/build.prop') or os.path.isdir('/data/data/com.termux')


def is_desktop_like() -> bool:
    return not is_android_like()


def _parse_ffmpeg_encoders(text: str) -> frozenset[str]:
    names: set[str] = set()
    for line in text.splitlines():
        match = re.match(r'\s*\S+\s+(\S+)', line)
        if match:
            names.add(match.group(1).strip().lower())
    return frozenset(names)


def list_ffmpeg_encoders(ffmpeg: str | None = None, *, refresh: bool = False) -> frozenset[str]:
    global _ENCODER_LISTING
    with _CACHE_LOCK:
        if _ENCODER_LISTING is not None and not refresh:
            return _ENCODER_LISTING

    ffmpeg = ffmpeg or locate_ffmpeg()
    if not ffmpeg:
        listing: frozenset[str] = frozenset()
    else:
        try:
            proc = subprocess.run(
                [ffmpeg, '-hide_banner', '-encoders'],
                capture_output=True,
                text=True,
                timeout=30,
                **_no_window_kwargs(),
            )
            text = (proc.stdout or '') + '\n' + (proc.stderr or '')
            listing = _parse_ffmpeg_encoders(text)
        except (OSError, subprocess.TimeoutExpired):
            listing = frozenset()

    with _CACHE_LOCK:
        _ENCODER_LISTING = listing
    return listing


def mediacodec_encoder_name(target_codec: str) -> str | None:
    codec = str(target_codec or 'h264').strip().lower()
    return _MEDIACODEC_ENCODERS.get(codec)


def mediacodec_listed(target_codec: str, ffmpeg: str | None = None) -> bool:
    name = mediacodec_encoder_name(target_codec)
    if not name:
        return False
    return name in list_ffmpeg_encoders(ffmpeg)


def _vaapi_render_nodes() -> list[str]:
    dri = '/dev/dri'
    if not os.path.isdir(dri):
        return []
    return [
        os.path.join(dri, name)
        for name in sorted(os.listdir(dri))
        if name.startswith('renderD') and os.path.exists(os.path.join(dri, name))
    ]


def resolve_vaapi_device() -> str | None:
    global _VAAPI_DEVICE, _VAAPI_DEVICE_CHECKED
    with _CACHE_LOCK:
        if _VAAPI_DEVICE_CHECKED:
            return _VAAPI_DEVICE
        _VAAPI_DEVICE_CHECKED = True
        nodes = _vaapi_render_nodes()
        _VAAPI_DEVICE = nodes[0] if nodes else None
    return _VAAPI_DEVICE


def _validation_cache_key(backend_id: str, encoder_name: str) -> tuple[str, str]:
    return backend_id, encoder_name


def _run_validation_cmd(ffmpeg: str, cmd: list[str]) -> bool:
    try:
        proc = subprocess.run(
            [ffmpeg, *cmd],
            capture_output=True,
            text=True,
            timeout=60,
            **_no_window_kwargs(),
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _probe_mediacodec_encoder(ffmpeg: str, encoder_name: str) -> bool:
    """Try several minimal encodes; Termux builds often reject lavfi/null probes."""
    null_tail = ['-b:v', '500k', '-g', '30', '-an', '-f', 'null', '-']
    lavfi_inputs = [
        ['-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=15'],
        ['-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=15'],
        ['-f', 'lavfi', '-i', 'color=c=black:s=128x128:r=25'],
    ]
    for lavfi in lavfi_inputs:
        base = [
            '-hide_banner', '-loglevel', 'error',
            *lavfi,
            '-t', '0.15', '-pix_fmt', 'yuv420p',
        ]
        for video_args in (
            ['-c:v', encoder_name, '-bitrate_mode', 'vbr'],
            ['-c:v', encoder_name],
        ):
            if _run_validation_cmd(ffmpeg, base + video_args + null_tail):
                return True

    fd, temp_path = tempfile.mkstemp(suffix='.mp4', prefix='jav-hw-probe-')
    os.close(fd)
    try:
        for video_args in (
            ['-c:v', encoder_name, '-bitrate_mode', 'vbr'],
            ['-c:v', encoder_name],
        ):
            cmd = [
                '-hide_banner', '-loglevel', 'error',
                '-f', 'lavfi', '-i', 'color=c=black:s=320x240:r=15',
                '-t', '0.2', '-pix_fmt', 'yuv420p',
                *video_args,
                '-b:v', '500k', '-g', '30', '-an',
                '-y', temp_path,
            ]
            if _run_validation_cmd(ffmpeg, cmd):
                try:
                    if os.path.getsize(temp_path) > 0:
                        return True
                except OSError:
                    pass
    finally:
        try:
            if os.path.isfile(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
    return False


def _mediacodec_trust_listed_encoder(ffmpeg: str, encoder_name: str) -> bool:
    """Android: ffmpeg lists MediaCodec but lavfi/null probes often fail anyway."""
    if not is_android_like():
        return False
    return encoder_name in list_ffmpeg_encoders(ffmpeg)


def validation_probe_passed(spec: HardwareEncoderSpec) -> bool:
    cache_key = _validation_cache_key(spec.backend_id, spec.encoder_name)
    with _CACHE_LOCK:
        entry = _VALIDATED.get(cache_key)
    if not entry:
        return False
    return bool(entry[1])


def validate_hardware_encoder(
        spec: HardwareEncoderSpec,
        ffmpeg: str | None = None,
        *,
        refresh: bool = False) -> bool:
    """Try a minimal encode to confirm the hardware encoder initializes."""
    cache_key = _validation_cache_key(spec.backend_id, spec.encoder_name)
    with _CACHE_LOCK:
        if not refresh and cache_key in _VALIDATED:
            return _VALIDATED[cache_key][0]

    ffmpeg = ffmpeg or locate_ffmpeg()
    ok = False
    probe_ok = False
    if ffmpeg and spec.encoder_name:
        base = [
            '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'testsrc2=size=64x64:rate=1',
            '-t', '0.04', '-pix_fmt', 'yuv420p',
        ]
        tail = ['-b:v', '200k', '-g', '30', '-an', '-f', 'null', '-']

        if spec.backend_id == 'mediacodec':
            probe_ok = _probe_mediacodec_encoder(ffmpeg, spec.encoder_name)
            ok = probe_ok
            if not ok:
                ok = _mediacodec_trust_listed_encoder(ffmpeg, spec.encoder_name)
        elif spec.backend_id == 'nvenc':
            ok = _run_validation_cmd(ffmpeg, base + [
                '-c:v', spec.encoder_name, '-preset', 'p4',
            ] + tail)
        elif spec.backend_id == 'qsv':
            ok = _run_validation_cmd(ffmpeg, base + [
                '-c:v', spec.encoder_name,
            ] + tail)
        elif spec.backend_id == 'vaapi':
            device = spec.vaapi_device or resolve_vaapi_device()
            if device:
                ok = _run_validation_cmd(ffmpeg, [
                    '-hide_banner', '-loglevel', 'error',
                    '-init_hw_device', f'vaapi=va:{device}',
                    '-filter_hw_device', 'va',
                    '-f', 'lavfi', '-i', 'testsrc2=size=64x64:rate=1',
                    '-t', '0.04',
                    '-vf', 'format=nv12,hwupload',
                    '-c:v', spec.encoder_name,
                    '-b:v', '200k', '-g', '30', '-an',
                    '-f', 'null', '-',
                ])
        elif spec.backend_id == 'videotoolbox':
            ok = _run_validation_cmd(ffmpeg, base + [
                '-c:v', spec.encoder_name,
            ] + tail)
            probe_ok = ok

    with _CACHE_LOCK:
        _VALIDATED[cache_key] = (ok, probe_ok)
    return ok


def _spec_for_backend(backend: dict, target_codec: str) -> HardwareEncoderSpec | None:
    codec = str(target_codec or 'h264').strip().lower()
    encoder = backend['encoders'].get(codec)
    if not encoder:
        return None
    vaapi_device = None
    if backend['id'] == 'vaapi':
        vaapi_device = resolve_vaapi_device()
        if not vaapi_device:
            return None
    platform_label = 'android' if backend['id'] == 'mediacodec' else 'desktop'
    return HardwareEncoderSpec(
        backend_id=backend['id'],
        encoder_name=encoder,
        platform=platform_label,
        vaapi_device=vaapi_device,
    )


def _backend_candidates(target_codec: str, ffmpeg: str | None = None) -> list[HardwareEncoderSpec]:
    encoders = list_ffmpeg_encoders(ffmpeg)
    specs: list[HardwareEncoderSpec] = []

    if is_android_like():
        spec = _spec_for_backend(
            {'id': 'mediacodec', 'encoders': _MEDIACODEC_ENCODERS},
            target_codec,
        )
        if spec and spec.encoder_name in encoders:
            specs.append(spec)
        return specs

    for backend in _DESKTOP_BACKENDS:
        spec = _spec_for_backend(backend, target_codec)
        if spec and spec.encoder_name in encoders:
            specs.append(spec)
    return specs


def resolve_hardware_encoder(
        target_codec: str,
        ffmpeg: str | None = None,
        *,
        validate: bool = True) -> tuple[bool, HardwareEncoderSpec | None, str | None]:
    """Return the best validated hardware encoder for this platform and codec."""
    candidates = _backend_candidates(target_codec, ffmpeg)
    if not candidates:
        if is_android_like():
            name = mediacodec_encoder_name(target_codec)
            if name:
                return False, None, f'{name} not in ffmpeg encoder list'
            return False, None, f'unsupported target codec {target_codec}'
        return False, None, 'no hardware encoder listed in ffmpeg'

    last_reason = 'hardware encoder initialization failed'
    for spec in candidates:
        if validate and not validate_hardware_encoder(spec, ffmpeg):
            last_reason = f'{spec.encoder_name} initialization failed'
            continue
        return True, spec, None

    fallback = candidates[0]
    return False, fallback, last_reason


def hardware_encoder_available(
        target_codec: str,
        ffmpeg: str | None = None,
        *,
        validate: bool = True) -> tuple[bool, str | None, str | None]:
    """Return (available, encoder_name, reason_if_unavailable)."""
    ok, spec, reason = resolve_hardware_encoder(
        target_codec, ffmpeg, validate=validate)
    if ok and spec:
        return True, spec.encoder_name, None
    encoder = spec.encoder_name if spec else None
    return False, encoder, reason


def hardware_capabilities_summary(
        ffmpeg: str | None = None,
        *,
        validate: bool = True) -> dict:
    """Structured capability map for API/UI consumption."""
    ffmpeg = ffmpeg or locate_ffmpeg()
    platform_label = 'android' if is_android_like() else 'desktop'
    codecs: dict[str, dict] = {}
    backends: dict[str, dict] = {}

    for codec in ('h264', 'hevc'):
        ok, spec, reason = resolve_hardware_encoder(codec, ffmpeg, validate=validate)
        probe_ok = validation_probe_passed(spec) if spec else False
        codecs[codec] = {
            'available': ok,
            'validated': probe_ok if ok else False,
            'encoder': spec.encoder_name if spec else None,
            'backend': spec.backend_id if spec else None,
            'reason': reason,
        }
        if spec:
            entry = backends.setdefault(spec.backend_id, {
                'id': spec.backend_id,
                'platform': spec.platform,
                'codecs': {},
            })
            entry['codecs'][codec] = {
                'available': ok,
                'validated': probe_ok if ok else False,
                'encoder': spec.encoder_name,
                'reason': reason if not ok else None,
            }

    return {
        'platform': platform_label,
        'codecs': codecs,
        'backends': backends,
    }


def clear_capability_cache() -> None:
    global _ENCODER_LISTING, _VAAPI_DEVICE, _VAAPI_DEVICE_CHECKED
    with _CACHE_LOCK:
        _ENCODER_LISTING = None
        _VALIDATED.clear()
        _VAAPI_DEVICE = None
        _VAAPI_DEVICE_CHECKED = False
