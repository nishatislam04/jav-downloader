"""Reveal a downloaded file in the system file manager."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def reveal_in_file_manager(path: str) -> None:
    """Open the file manager with the given file or folder highlighted."""
    target = Path(path).expanduser().resolve()
    if not target.exists():
        raise ValueError('Path does not exist')

    if sys.platform == 'darwin':
        subprocess.Popen(['open', '-R', str(target)], start_new_session=True)
        return

    if sys.platform == 'win32':
        subprocess.Popen(['explorer', f'/select,{target}'], start_new_session=True)
        return

    file_arg = str(target)
    parent_arg = str(target.parent)
    for executable, args in (
        ('dolphin', ['--select', file_arg]),
        ('nautilus', ['--select', file_arg]),
        ('nemo', ['--no-desktop', parent_arg]),
        ('thunar', [parent_arg]),
        ('pcmanfm', [parent_arg]),
        ('xdg-open', [parent_arg]),
    ):
        binary = shutil.which(executable)
        if not binary:
            continue
        subprocess.Popen([binary, *args], start_new_session=True)
        return

    raise ValueError('No file manager available')
