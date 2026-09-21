"""Reveal a downloaded file in the system file manager."""

from __future__ import annotations

import mimetypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

_TERMUX_STORAGE_MAP = {
    "downloads": "Download",
    "dcim": "DCIM",
    "pictures": "Pictures",
    "movies": "Movies",
    "music": "Music",
    "documents": "Documents",
}


def is_termux_like() -> bool:
    """True when running inside Termux on Android."""
    if os.environ.get("TERMUX_VERSION"):
        return True
    prefix = os.environ.get("PREFIX", "")
    return prefix.startswith("/data/data/com.termux")


def reveal_mode() -> str:
    """UI hint: Android opens the file; desktop reveals in file manager."""
    return "open_file" if is_termux_like() else "show_in_folder"


def _guess_mime_type(path: Path) -> str:
    mime, _encoding = mimetypes.guess_type(str(path))
    if mime:
        return mime
    if path.suffix.lower() == ".mp4":
        return "video/mp4"
    if path.suffix.lower() in {".mkv", ".webm"}:
        return "video/*"
    return "application/octet-stream"


def _android_open_paths(target: Path) -> list[Path]:
    """Return candidate paths termux-open may accept."""
    candidates: list[Path] = []
    resolved = target.resolve()
    candidates.append(resolved)

    storage_root = Path.home() / "storage"
    try:
        rel = resolved.relative_to(storage_root)
    except ValueError:
        return candidates

    if not rel.parts:
        return candidates

    mapped = _TERMUX_STORAGE_MAP.get(rel.parts[0].lower(), rel.parts[0])
    alt = Path("/storage/emulated/0") / mapped / Path(*rel.parts[1:])
    if alt != resolved:
        candidates.append(alt)
    return list(dict.fromkeys(candidates))


def _run_command(cmd: list[str]) -> None:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise ValueError(f"Command not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Timed out running {cmd[0]}") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ValueError(detail or f"{cmd[0]} exited with code {proc.returncode}")


def _termux_open(target: Path) -> None:
    binary = shutil.which("termux-open")
    if not binary:
        raise ValueError("termux-open not found — run: pkg install termux-tools")

    mime = _guess_mime_type(target)
    errors: list[str] = []
    for candidate in _android_open_paths(target):
        if not candidate.is_file():
            errors.append(f"{candidate}: not a readable file")
            continue
        for extra in ([], ["--chooser"]):
            cmd = [binary, "--view", "--content-type", mime, *extra, str(candidate)]
            try:
                _run_command(cmd)
                return
            except ValueError as exc:
                errors.append(f"{' '.join(cmd)}: {exc}")

    hint = (
        "Could not open file on Android. Enable "
        "'Allow external apps' in Termux settings, run termux-reload-settings, "
        "and ensure termux-setup-storage was granted."
    )
    detail = "; ".join(errors[-3:]) if errors else "unknown error"
    raise ValueError(f"{hint} ({detail})")


def reveal_in_file_manager(path: str) -> None:
    """Open the file manager with the given file or folder highlighted."""
    target = Path(path).expanduser()
    if not target.exists():
        raise ValueError("Path does not exist")
    target = target.resolve()

    if is_termux_like() and sys.platform == "linux":
        _termux_open(target)
        return

    if sys.platform == "darwin":
        _run_command(["open", "-R", str(target)])
        return

    if sys.platform == "win32":
        _run_command(["explorer", f"/select,{target}"])
        return

    file_arg = str(target)
    parent_arg = str(target.parent)
    for executable, args in (
        ("dolphin", ["--select", file_arg]),
        ("nautilus", ["--select", file_arg]),
        ("nemo", ["--no-desktop", parent_arg]),
        ("thunar", [parent_arg]),
        ("pcmanfm", [parent_arg]),
        ("xdg-open", [parent_arg]),
    ):
        binary = shutil.which(executable)
        if not binary:
            continue
        _run_command([binary, *args])
        return

    raise ValueError("No file manager available")
