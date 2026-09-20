"""Remove leftover partial files from cancelled or crashed downloads.

The sweep only touches artifact patterns this app creates inside the
download folder itself (top level):

- temp workdirs: ``jav-remux-*``, ``jav-multicut-*``, ``jav-hlsmulticut-*``
- temp media:    ``jav-encode-*.mp4``, ``jav-audio-*.mp4``, ``jav-cut-*.mp4``
- partial file:  ``*.mp4.part``
- segment dirs:  a top-level directory whose entries are all ``NNNNNN.mp4``
  segment files — the HLS temp-folder pattern

Completed videos, user files, and any folder with mixed content are never
touched. Every delete target must resolve strictly inside the download
directory. Each step is reported through an optional ``on_event`` callback
so the web UI job log can show the sweep in detail.
"""

from __future__ import annotations

import os
import re
import shutil

WORKDIR_PREFIXES = ("jav-remux-", "jav-multicut-", "jav-hlsmulticut-")
TEMP_FILE_PREFIXES = ("jav-encode-", "jav-audio-", "jav-cut-", "jav-hlsmulticut-")
_PART_SUFFIX = ".part"
_SEGMENT_NAME_RE = re.compile(r"^\d{6}\.mp4$")


def _contained(path: str, root: str) -> bool:
    """True when path resolves strictly inside root (symlinks resolved)."""
    real_root = os.path.realpath(root)
    real_path = os.path.realpath(path)
    return real_path != real_root and real_path.startswith(real_root + os.sep)


def _tree_size(path: str) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, filename))
            except OSError:
                pass
    return total


def _is_segment_dir(path: str) -> bool:
    """True when every entry looks like an HLS segment (NNNNNN.mp4)."""
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    if not entries:
        return False
    return all(_SEGMENT_NAME_RE.match(entry) for entry in entries)


def _fmt_size(num: float) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def sweep_dest_folder(dest_folder: str, on_event=None) -> dict:
    """Remove known partial artifacts under dest_folder. Never recurses
    into user directories; scans the top level only."""
    result = {
        "ok": False,
        "removed_files": 0,
        "removed_dirs": 0,
        "freed_bytes": 0,
        "skipped": 0,
        "error": "",
    }

    def emit(message: str) -> None:
        if on_event is None:
            return
        try:
            on_event(message)
        except Exception:
            pass

    root = os.path.realpath(os.path.expanduser(dest_folder or ""))
    if not os.path.isdir(root):
        result["error"] = "Download directory does not exist"
        return result

    emit(f"Scanning {root}")
    try:
        entries = sorted(os.listdir(root))
    except OSError as exc:
        result["error"] = str(exc)
        emit(f"Scan failed: {exc}")
        return result

    for name in entries:
        path = os.path.join(root, name)
        if not _contained(path, root):
            result["skipped"] += 1
            emit(f"Skipped {name} (outside download folder)")
            continue
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                if name.startswith(WORKDIR_PREFIXES) or _is_segment_dir(path):
                    size = _tree_size(path)
                    emit(f"Removing folder {name}/ ({_fmt_size(size)})")
                    shutil.rmtree(path, ignore_errors=True)
                    if os.path.exists(path):
                        result["skipped"] += 1
                        emit(f"Could not fully remove folder {name}/ (in use?)")
                    else:
                        result["freed_bytes"] += size
                        result["removed_dirs"] += 1
            elif os.path.isfile(path):
                if name.startswith(TEMP_FILE_PREFIXES) or name.endswith(_PART_SUFFIX):
                    size = os.path.getsize(path)
                    emit(f"Removing {name} ({_fmt_size(size)})")
                    os.remove(path)
                    result["freed_bytes"] += size
                    result["removed_files"] += 1
        except OSError as exc:
            result["skipped"] += 1
            emit(f"Skipped {name}: {exc}")

    if result["removed_files"] or result["removed_dirs"]:
        emit(
            f"Cleanup complete: {result['removed_files']} files, "
            f"{result['removed_dirs']} folders, "
            f"{_fmt_size(result['freed_bytes'])} freed"
        )
    else:
        emit("Nothing to clean up")
    result["ok"] = True
    return result


def cleanup_job(manager, job_id: str) -> dict:
    """Sweep a stopped job's download folder after user confirmation."""
    from jav_downloader.web.jobs import JobStatus
    from jav_downloader.web.paths import default_download_dir

    job = manager.get(job_id)
    if job is None:
        return {"ok": False, "error": "Job not found"}

    # Imported lazily: service pulls in the site crawlers.
    from jav_downloader.web import service

    with service._active_lock:
        active = job_id in service._active_downloads
    if active or job.status in (JobStatus.DOWNLOADING, JobStatus.PENDING):
        return {"ok": False, "error": "Job is still running — cancel it first"}

    dest = job.dest_folder or ""
    if not dest:
        params = service._job_params.get(job_id) or {}
        dest = params.get("dest") or ""
    if not dest:
        dest = default_download_dir()

    def on_event(message: str) -> None:
        manager.append_log(job_id, f"[{service._log_stamp()}] {message}")

    result = sweep_dest_folder(dest, on_event)
    if not result["ok"]:
        on_event(f"Cleanup failed: {result['error']}")
    return result
