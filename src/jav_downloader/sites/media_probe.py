#!/usr/bin/env python
# coding: utf-8
"""Inspect local media files via ffprobe for encoding decisions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass

from jav_downloader.sites.base import locate_ffmpeg, _no_window_kwargs

_FFPROBE_PATH = None
_FFPROBE_RESOLVED = False

_H264_NAMES = frozenset({'h264', 'avc1', 'avc', 'libx264'})
_HEVC_NAMES = frozenset({'hevc', 'h265', 'hev1', 'hvc1', 'libx265'})


@dataclass(frozen=True)
class VideoStreamInfo:
    codec_name: str
    width: int
    height: int
    pix_fmt: str

    def normalized_codec(self) -> str | None:
        name = str(self.codec_name or '').strip().lower()
        if name in _H264_NAMES or name.startswith('h264'):
            return 'h264'
        if name in _HEVC_NAMES or name.startswith('hevc') or name.startswith('h265'):
            return 'hevc'
        return name or None


@dataclass(frozen=True)
class AudioStreamInfo:
    codec_name: str


@dataclass(frozen=True)
class MediaInfo:
    path: str
    duration_sec: float | None
    video: VideoStreamInfo | None
    audio: AudioStreamInfo | None
    container: str


def _ffprobe_works(path: str) -> bool:
    try:
        proc = subprocess.run(
            [path, '-version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            **_no_window_kwargs(),
        )
        return proc.returncode == 0
    except Exception:
        return False


def locate_ffprobe() -> str | None:
    """Return ffprobe path (alongside ffmpeg, then PATH)."""
    global _FFPROBE_PATH, _FFPROBE_RESOLVED
    if _FFPROBE_RESOLVED:
        return _FFPROBE_PATH

    candidates = []
    ffmpeg = locate_ffmpeg()
    if ffmpeg:
        ff_dir = os.path.dirname(os.path.abspath(ffmpeg))
        name = 'ffprobe.exe' if os.name == 'nt' else 'ffprobe'
        candidates.append(os.path.join(ff_dir, name))
    which = shutil.which('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
    if which:
        candidates.append(which)

    chosen = None
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and _ffprobe_works(candidate):
            chosen = candidate
            break
    _FFPROBE_PATH = chosen
    _FFPROBE_RESOLVED = True
    return chosen


def _parse_stream_entry(entry: dict, kind: str):
    if str(entry.get('codec_type') or '').lower() != kind:
        return None
    if kind == 'video':
        try:
            width = int(entry.get('width') or 0)
            height = int(entry.get('height') or 0)
        except (TypeError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return VideoStreamInfo(
            codec_name=str(entry.get('codec_name') or ''),
            width=width,
            height=height,
            pix_fmt=str(entry.get('pix_fmt') or ''),
        )
    if kind == 'audio':
        codec = str(entry.get('codec_name') or '').strip()
        if not codec:
            return None
        return AudioStreamInfo(codec_name=codec)
    return None


def _parse_probe_json(path: str, payload: dict) -> MediaInfo:
    fmt = payload.get('format') or {}
    duration = None
    try:
        raw = fmt.get('duration')
        if raw is not None:
            duration = float(raw)
    except (TypeError, ValueError):
        duration = None

    video = None
    audio = None
    for entry in payload.get('streams') or []:
        if video is None:
            video = _parse_stream_entry(entry, 'video')
        if audio is None:
            audio = _parse_stream_entry(entry, 'audio')

    container = str(fmt.get('format_name') or os.path.splitext(path)[1].lstrip('.'))
    return MediaInfo(
        path=path,
        duration_sec=duration,
        video=video,
        audio=audio,
        container=container,
    )


def probe_media(path: str) -> MediaInfo | None:
    """Return stream metadata for a local file, or None when probing fails."""
    if not path or not os.path.isfile(path):
        return None
    ffprobe = locate_ffprobe()
    if not ffprobe:
        return None
    cmd = [
        ffprobe,
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_streams',
        '-show_format',
        path,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            **_no_window_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return _parse_probe_json(path, payload)
