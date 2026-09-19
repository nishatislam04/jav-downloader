#!/usr/bin/env python
# coding: utf-8
"""Optional ffmpeg audio post-processing (fade, loudness normalize)."""

from __future__ import annotations

import os
import subprocess
import tempfile

from jav_downloader.sites.base import locate_ffmpeg, _no_window_kwargs

FADE_SEC = 0.5


def site_wants_fade(site) -> bool:
    return bool(getattr(site, '_audio_fade', False))


def site_wants_loudnorm(site) -> bool:
    return bool(getattr(site, '_audio_loudnorm', False))


def needs_audio_processing(site) -> bool:
    return site_wants_fade(site) or site_wants_loudnorm(site)


def build_af_filter(site, duration_sec: float | None) -> str | None:
    parts = []
    duration = float(duration_sec or 0)
    if site_wants_fade(site) and duration > 0:
        fade = min(FADE_SEC, duration / 2)
        parts.append(f'afade=t=in:st=0:d={fade:g}')
        if duration > fade * 2:
            parts.append(f'afade=t=out:st={duration - fade:g}:d={fade:g}')
    if site_wants_loudnorm(site):
        parts.append('loudnorm')
    return ','.join(parts) if parts else None


def append_ffmpeg_output_args(cmd, site, duration_sec: float | None = None) -> None:
    af = build_af_filter(site, duration_sec)
    if af:
        cmd.extend(['-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', af])
    else:
        cmd.extend(['-c', 'copy'])
    cmd.extend(['-movflags', '+faststart'])


def post_process_audio(site, src_path: str, duration_sec: float | None = None) -> None:
    """Rewrite src_path in place when fade/loudnorm is enabled."""
    if not needs_audio_processing(site):
        return
    if not src_path or not os.path.isfile(src_path):
        return

    ffmpeg = locate_ffmpeg()
    if not ffmpeg:
        raise Exception('Audio processing requires ffmpeg')

    af = build_af_filter(site, duration_sec)
    if not af:
        return

    dest_dir = os.path.dirname(src_path) or os.getcwd()
    fd, temp_path = tempfile.mkstemp(suffix='.mp4', prefix='jav-audio-', dir=dest_dir)
    os.close(fd)
    cmd = [
        ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
        '-i', src_path,
        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-af', af,
        '-movflags', '+faststart', temp_path,
    ]
    proc = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        **_no_window_kwargs(),
    )
    if proc.returncode != 0 or not os.path.isfile(temp_path) or os.path.getsize(temp_path) <= 0:
        _safe_remove(temp_path)
        detail = (proc.stderr or proc.stdout or '').strip() or f'ffmpeg exit {proc.returncode}'
        raise Exception(f'Audio processing failed: {detail}')
    os.replace(temp_path, src_path)


def _safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
