#!/usr/bin/env python
# coding: utf-8
"""Safe application-level performance helpers (no root/kernel changes)."""

from __future__ import annotations

import os
import shutil
import subprocess
from contextlib import contextmanager

from jav_downloader.sites.base import _no_window_kwargs
from jav_downloader.sites.encoding_capabilities import is_android_like


def needs_video_scale(source_height: int | None, max_height: int) -> bool:
    """True when a scale filter is required for the requested max height."""
    if max_height <= 0:
        return False
    if source_height is None or source_height <= 0:
        return True
    return int(source_height) > max_height


def cached_probe_media(site, path: str):
    """Return cached MediaInfo for path on this site object when available."""
    from jav_downloader.sites.media_probe import probe_media

    cache = getattr(site, '_media_probe_cache', None)
    if isinstance(cache, dict) and cache.get('path') == path:
        return cache.get('info')
    info = probe_media(path)
    site._media_probe_cache = {'path': path, 'info': info}
    return info


class _WakeLock:
    """Best-effort Termux partial wake lock; no-op elsewhere or when unavailable."""

    def __init__(self):
        self._active = False

    def acquire(self) -> None:
        if not is_android_like() or self._active:
            return
        lock_cmd = shutil.which('termux-wake-lock')
        if not lock_cmd:
            return
        try:
            proc = subprocess.run(
                [lock_cmd],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                **_no_window_kwargs(),
            )
            if proc.returncode == 0:
                self._active = True
        except (OSError, subprocess.TimeoutExpired):
            pass

    def release(self) -> None:
        if not self._active:
            return
        unlock_cmd = shutil.which('termux-wake-unlock')
        self._active = False
        if not unlock_cmd:
            return
        try:
            subprocess.run(
                [unlock_cmd],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                **_no_window_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


@contextmanager
def ffmpeg_work_session(site=None):
    """Hold an Android wake lock for the duration of ffmpeg work when possible."""
    lock = _WakeLock()
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
