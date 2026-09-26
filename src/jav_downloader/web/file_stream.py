"""Stream local media files over HTTP with Range support (in-browser playback)."""

from __future__ import annotations

import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path

_CHUNK = 1024 * 512


def _safe_job_output_path(job) -> Path | None:
    raw = str(getattr(job, "output_file", "") or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        return None
    dest = str(getattr(job, "dest_folder", "") or "").strip()
    if dest:
        try:
            path.relative_to(Path(dest).expanduser().resolve())
        except ValueError:
            return None
    return path


def serve_job_output(handler: BaseHTTPRequestHandler, job) -> None:
    """Write job output file to handler.wfile with Accept-Ranges."""
    path = _safe_job_output_path(job)
    if path is None:
        handler.send_error(HTTPStatus.NOT_FOUND, "Output file not available")
        return
    _serve_file(handler, path)


def _parse_range(range_header: str, size: int) -> tuple[int, int] | None:
    if not range_header or not range_header.strip().lower().startswith("bytes="):
        return None
    spec = range_header.split("=", 1)[1].strip()
    if "," in spec:
        return None
    start_text, _, end_text = spec.partition("-")
    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
        elif end_text:
            suffix = int(end_text)
            start = max(0, size - suffix)
            end = size - 1
        else:
            return None
    except ValueError:
        return None
    if start < 0 or end >= size or start > end:
        return None
    return start, end


def _serve_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    size = path.stat().st_size
    mime, _encoding = mimetypes.guess_type(str(path))
    if not mime and path.suffix.lower() == ".mp4":
        mime = "video/mp4"
    content_type = mime or "application/octet-stream"

    byte_range = _parse_range(handler.headers.get("Range", ""), size)
    if byte_range is None:
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(size))
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Cache-Control", "private, max-age=3600")
        handler.end_headers()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(_CHUNK)
                if not chunk:
                    break
                handler.wfile.write(chunk)
        return

    start, end = byte_range
    length = end - start + 1
    handler.send_response(HTTPStatus.PARTIAL_CONTENT)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(length))
    handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Cache-Control", "private, max-age=3600")
    handler.end_headers()
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(_CHUNK, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)
