#!/usr/bin/env python
# coding: utf-8
"""Runtime detection of FFmpeg encoder capabilities (MediaCodec, etc.)."""

from __future__ import annotations

import os
import platform
import re
import subprocess
import threading

from jav_downloader.sites.base import _no_window_kwargs, locate_ffmpeg

_CACHE_LOCK = threading.Lock()
_ENCODER_LISTING: frozenset[str] | None = None
_MEDIACODEC_VALIDATED: dict[str, bool] = {}

_HARDWARE_VIDEO_ENCODERS = {
    'h264': 'h264_mediacodec',
    'hevc': 'hevc_mediacodec',
}


def is_android_like() -> bool:
    if os.environ.get('TERMUX_VERSION'):
        return True
    if platform.system().lower() != 'linux':
        return False
    return os.path.isfile('/system/build.prop') or os.path.isdir('/data/data/com.termux')


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
    return _HARDWARE_VIDEO_ENCODERS.get(codec)


def mediacodec_listed(target_codec: str, ffmpeg: str | None = None) -> bool:
    name = mediacodec_encoder_name(target_codec)
    if not name:
        return False
    return name in list_ffmpeg_encoders(ffmpeg)


def validate_mediacodec_encoder(
        encoder_name: str,
        ffmpeg: str | None = None,
        *,
        refresh: bool = False) -> bool:
    """Try a minimal encode to confirm MediaCodec initializes."""
    with _CACHE_LOCK:
        if not refresh and encoder_name in _MEDIACODEC_VALIDATED:
            return _MEDIACODEC_VALIDATED[encoder_name]

    ffmpeg = ffmpeg or locate_ffmpeg()
    ok = False
    if ffmpeg and encoder_name:
        cmd = [
            ffmpeg, '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'testsrc2=size=64x64:rate=1',
            '-t', '0.04', '-pix_fmt', 'yuv420p',
            '-c:v', encoder_name,
            '-bitrate_mode', 'vbr', '-b:v', '200k',
            '-g', '30', '-an',
            '-f', 'null', '-',
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=45,
                **_no_window_kwargs(),
            )
            ok = proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False

    with _CACHE_LOCK:
        _MEDIACODEC_VALIDATED[encoder_name] = ok
    return ok


def hardware_encoder_available(
        target_codec: str,
        ffmpeg: str | None = None,
        *,
        validate: bool = True) -> tuple[bool, str | None, str | None]:
    """Return (available, encoder_name, reason_if_unavailable)."""
    if not is_android_like():
        return False, None, 'not Android'

    name = mediacodec_encoder_name(target_codec)
    if not name:
        return False, None, f'unsupported target codec {target_codec}'

    if not mediacodec_listed(target_codec, ffmpeg):
        return False, name, f'{name} not in ffmpeg encoder list'

    if validate and not validate_mediacodec_encoder(name, ffmpeg):
        return False, name, f'{name} initialization failed'

    return True, name, None


def clear_capability_cache() -> None:
    global _ENCODER_LISTING
    with _CACHE_LOCK:
        _ENCODER_LISTING = None
        _MEDIACODEC_VALIDATED.clear()
