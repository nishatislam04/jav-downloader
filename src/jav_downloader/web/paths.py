"""Default output paths for the web UI."""

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
