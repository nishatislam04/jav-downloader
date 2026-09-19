"""Default output paths and save-location validation for the web UI."""

from __future__ import annotations

import os
from pathlib import Path


def default_download_dir() -> str:
    """Return the best writable Downloads folder for the current platform."""
    env = os.environ.get('DOWNLOAD_DIR', '').strip()
    if env:
        return os.path.abspath(os.path.expanduser(env))

    home = Path.home()
    candidates = (
        home / 'storage' / 'downloads',  # Termux after termux-setup-storage
        home / 'Downloads',
        home / 'Download',
        Path('/downloads'),
    )
    for path in candidates:
        expanded = path.expanduser()
        if expanded.is_dir():
            return str(expanded.resolve())

    fallback = home / 'Downloads'
    fallback.mkdir(parents=True, exist_ok=True)
    return str(fallback.resolve())


def validate_dest_folder(path: str | None) -> str:
    """Return a normalized folder path or raise ValueError when unusable."""
    text = str(path or '').strip()
    if not text:
        return default_download_dir()

    resolved = Path(os.path.abspath(os.path.expanduser(text))).resolve()
    if not resolved.is_dir():
        raise ValueError('Save location must be an existing folder')
    if not os.access(resolved, os.W_OK):
        raise ValueError('Save location is not writable')

    return str(resolved)
