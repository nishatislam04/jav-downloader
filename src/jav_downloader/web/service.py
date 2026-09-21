"""Resolve URLs and run background downloads for the web UI."""

from __future__ import annotations

import os
import threading
import time

from jav_downloader import sites
from jav_downloader.core import config
from jav_downloader.sites.base import (
    _apply_filename_mode,
    _sanitize_filename,
    _truncate_target_name,
)
from jav_downloader.web.job_store import JobStore
from jav_downloader.web.jobs import Job, JobManager, JobStatus
from jav_downloader.web.paths import default_download_dir, validate_dest_folder
from jav_downloader.web.progress_phase import phase_from_log

_active_downloads: dict[str, object] = {}
_active_lock = threading.Lock()
_job_params: dict[str, dict] = {}
_job_store_instance: JobStore | None = None


def _log_stamp() -> str:
    """Local 12-hour timestamp like `2:05:09 PM` for progress log lines.

    Computed manually (not via %I/%p) so locale quirks can never yield 24h.
    """
    now = time.localtime()
    hour12 = now.tm_hour % 12 or 12
    suffix = "AM" if now.tm_hour < 12 else "PM"
    return f"{hour12}:{now.tm_min:02d}:{now.tm_sec:02d} {suffix}"


def _site_label(site_cls) -> str:
    return getattr(site_cls, "direct_site_name", None) or site_cls.__name__


def _optional_time(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in ("1", "true", "yes", "on")


def _optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _audio_options(
    audio_fade=False,
    audio_loudnorm=False,
    audio_mute=False,
    audio_bitrate=None,
    audio_volume=None,
) -> dict:
    return {
        "audio_fade": bool(audio_fade),
        "audio_loudnorm": bool(audio_loudnorm),
        "audio_mute": bool(audio_mute),
        "audio_bitrate": _optional_int(audio_bitrate),
        "audio_volume": _optional_float(audio_volume),
    }


def _audio_options_from_mapping(payload: dict | None) -> dict:
    if not payload:
        return _audio_options()
    return _audio_options(
        audio_fade=_optional_bool(payload.get("audio_fade")),
        audio_loudnorm=_optional_bool(payload.get("audio_loudnorm")),
        audio_mute=_optional_bool(payload.get("audio_mute")),
        audio_bitrate=payload.get("audio_bitrate"),
        audio_volume=payload.get("audio_volume"),
    )


def _encode_options(
    encode=False,
    encode_codec=None,
    encode_crf=None,
    encode_max_height=None,
    encode_output_mode=None,
    encode_preset=None,
    encode_threads=None,
    encode_engine=None,
    encode_hardware_bitrate_kbps=None,
    encode_hardware_gop=None,
    encode_hardware_bitrate_mode=None,
) -> dict:
    return {
        "encode": bool(encode),
        "encode_codec": _optional_text(encode_codec),
        "encode_crf": _optional_int(encode_crf),
        "encode_max_height": _optional_int(encode_max_height),
        "encode_output_mode": _optional_text(encode_output_mode),
        "encode_preset": _optional_text(encode_preset),
        "encode_threads": _optional_int(encode_threads),
        "encode_engine": _optional_text(encode_engine),
        "encode_hardware_bitrate_kbps": _optional_int(encode_hardware_bitrate_kbps),
        "encode_hardware_gop": _optional_int(encode_hardware_gop),
        "encode_hardware_bitrate_mode": _optional_text(encode_hardware_bitrate_mode),
    }


def _encode_options_from_mapping(payload: dict | None) -> dict:
    if not payload:
        return _encode_options()
    return _encode_options(
        encode=_optional_bool(payload.get("encode")),
        encode_codec=payload.get("encode_codec"),
        encode_crf=payload.get("encode_crf"),
        encode_max_height=payload.get("encode_max_height"),
        encode_output_mode=payload.get("encode_output_mode"),
        encode_preset=payload.get("encode_preset"),
        encode_threads=payload.get("encode_threads"),
        encode_engine=payload.get("encode_engine"),
        encode_hardware_bitrate_kbps=payload.get("encode_hardware_bitrate_kbps"),
        encode_hardware_gop=payload.get("encode_hardware_gop"),
        encode_hardware_bitrate_mode=payload.get("encode_hardware_bitrate_mode"),
    )


def encoding_capabilities_payload() -> dict:
    from jav_downloader.sites.encoding_capabilities import hardware_capabilities_summary

    summary = hardware_capabilities_summary()
    hardware_codecs = {}
    for codec, info in (summary.get("codecs") or {}).items():
        hardware_codecs[codec] = {
            "available": bool(info.get("available")),
            "encoder": info.get("encoder"),
            "backend": info.get("backend"),
            "reason": info.get("reason"),
        }
    return {
        "ok": True,
        "platform": summary.get("platform", "desktop"),
        "hardware_codecs": hardware_codecs,
        "hardware_backends": summary.get("backends") or {},
        "hardware_bitrate_modes": ["vbr", "cbr"],
    }


def _site_resolve_extras(site) -> dict:
    from jav_downloader.sites.output_meta import (
        estimate_output_size,
        populate_hls_tiers,
    )

    populate_hls_tiers(site)
    size_bytes, size_exact = estimate_output_size(site)
    extras = {
        "output_size_bytes": size_bytes,
        "output_size_exact": bool(size_exact) if size_bytes else False,
    }
    if getattr(site, "_direct_url", None):
        extras["stream_type"] = "mp4"
    elif getattr(site, "_m3u8url", None):
        extras["stream_type"] = "hls"
    tiers = getattr(site, "_hls_tiers", None) or []
    if tiers:
        extras["hls_tiers"] = [
            {
                "id": tier.get("id"),
                "label": tier.get("label"),
                "height": tier.get("height"),
                "bandwidth": tier.get("bandwidth"),
                "pref": tier.get("pref"),
            }
            for tier in tiers
        ]
    return extras


def set_job_store_dest(dest_folder: str) -> None:
    """Point the job store at the server's download dir (startup)."""
    global _job_store_instance
    _job_store_instance = JobStore(dest_folder)


def _job_store() -> JobStore:
    """Job store rooted at the default download dir (lazy fallback)."""
    if _job_store_instance is None:
        set_job_store_dest(default_download_dir())
    return _job_store_instance


def restore_saved_jobs(manager: JobManager) -> int:
    """Load persisted jobs at startup; returns the count restored.

    Restored paused jobs keep their original id, so /resume keeps
    working across restarts. Their dest folder travels with them.
    """
    jobs, params_by_id = _job_store().load()
    restored = 0
    for job in jobs:
        if manager.get(job.id) is not None:
            continue
        params = params_by_id.get(job.id)
        if job.status == JobStatus.PAUSED and params:
            _job_params[job.id] = params
        restored += 1
    if restored:
        manager.restore_jobs(jobs)
    return restored


def persist_job_snapshot(jobs) -> None:
    """JobManager persistence hook: snapshot resumable jobs + params."""
    _job_store().save(jobs, _job_params)


def _apply_output_title(site, output_title: str | None) -> None:
    text = _optional_text(output_title)
    if not text or site is None:
        return
    name = _sanitize_filename(text)
    name = _apply_filename_mode(name, site._filename_mode)
    if not name.strip():
        return
    site._targetName = _truncate_target_name(name, site._dest_folder, site._dirName)


def resolve_url(
    url: str,
    dest_folder: str | None = None,
    cut_start: str | None = None,
    cut_end: str | None = None,
    cuts: list | None = None,
    output_title: str | None = None,
    audio_fade: bool = False,
    audio_loudnorm: bool = False,
    audio_mute: bool = False,
    audio_bitrate: int | None = None,
    audio_volume: float | None = None,
    **encode_kwargs,
) -> dict:
    """Collect metadata for a supported URL without starting a download."""
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "URL is required"}

    site_cls = sites.validate_url(url)
    if site_cls is None:
        return {"ok": False, "error": "Unsupported URL"}

    try:
        dest = validate_dest_folder(dest_folder)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    os.makedirs(dest, exist_ok=True)

    try:
        site = sites.create_site(
            url,
            savepath=dest,
            silence=True,
            cut_start=_optional_time(cut_start),
            cut_end=_optional_time(cut_end),
            cuts=cuts,
            **_audio_options(
                audio_fade=audio_fade,
                audio_loudnorm=audio_loudnorm,
                audio_mute=audio_mute,
                audio_bitrate=audio_bitrate,
                audio_volume=audio_volume,
            ),
            **_encode_options(**encode_kwargs),
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    if site is None:
        return {"ok": False, "error": "Unsupported URL"}

    try:
        _apply_output_title(site, output_title)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    if not site.is_url_vaildate():
        message = getattr(site, "_last_error", None)
        return {
            "ok": False,
            "error": str(message) if message else "Could not resolve video metadata",
        }

    return {
        "ok": True,
        "url": url,
        "site": _site_label(site_cls),
        "title": site.target_name() or "",
        "thumbnail": getattr(site, "_imageUrl", None) or "",
        "dest_folder": site.dest_folder() or dest,
        "exists": site.is_target_video_exist(),
        "duration_sec": getattr(site, "_duration_sec", None),
        "quality": getattr(site, "_quality_label", None) or "",
        "views": getattr(site, "_views_label", None) or "",
        "uploader": getattr(site, "_uploader", None) or "",
        **_site_resolve_extras(site),
    }


def _format_hms(seconds):
    """Format seconds as H:MM:SS for the config log block."""
    total = max(0, int(float(seconds)))
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _yes_no(value):
    return "on" if value else "off"


def _format_cut_ranges(ranges):
    parts = []
    for start, end in ranges or []:
        end_text = _format_hms(end) if end is not None else "end"
        parts.append(f"{_format_hms(start)}-{end_text}")
    return ", ".join(parts)


def _kv(pairs):
    return ", ".join(f"{key}={value}" for key, value in pairs if value is not None)


def _config_log_lines(site, output_title=None):
    """Effective job settings as [config] key: value lines for the UI log."""
    lines = [f"[config] dest: {site.dest_folder() or ''}"]
    lines.append(f"[config] resolution: {config.get_resolution_pref()}")
    lines.append(
        f"[config] filename_mode: {getattr(site, '_filename_mode', None) or '-'}"
    )
    lines.append(f"[config] workers: {getattr(site, '_max_workers', None) or '-'}")

    cuts_text = _format_cut_ranges(getattr(site, "_cut_ranges", None))
    if cuts_text:
        lines.append(f"[config] cuts: {cuts_text}")

    if output_title:
        lines.append(f"[config] output_title: {output_title}")

    if getattr(site, "_encode_enabled", False):
        lines.append("[config] encode: on")
        settings = _kv(
            [
                ("codec", getattr(site, "_encode_codec", None)),
                ("crf", getattr(site, "_encode_crf", None)),
                ("preset", getattr(site, "_encode_preset", None)),
                ("threads", getattr(site, "_encode_threads", None)),
                ("max_height", getattr(site, "_encode_max_height", None)),
                ("output_mode", getattr(site, "_encode_output_mode", None)),
            ]
        )
        if settings:
            lines.append(f"[config] encode_options: {settings}")
        engine = getattr(site, "_encode_engine", None)
        if engine and engine != "software":
            hw = _kv(
                [
                    ("engine", engine),
                    (
                        "bitrate_kbps",
                        getattr(site, "_encode_hardware_bitrate_kbps", None),
                    ),
                    ("gop", getattr(site, "_encode_hardware_gop", None)),
                    (
                        "bitrate_mode",
                        getattr(site, "_encode_hardware_bitrate_mode", None),
                    ),
                ]
            )
            if hw:
                lines.append(f"[config] encode_hw: {hw}")
    else:
        lines.append("[config] encode: off")

    audio = [
        getattr(site, "_audio_mute", False),
        getattr(site, "_audio_fade", False),
        getattr(site, "_audio_loudnorm", False),
        getattr(site, "_audio_bitrate", None),
        getattr(site, "_audio_volume", None),
    ]
    if any(audio):
        audio_kv = _kv(
            [
                ("mute", _yes_no(audio[0])),
                ("fade", _yes_no(audio[1])),
                ("loudnorm", _yes_no(audio[2])),
                ("bitrate", audio[3] if audio[3] is not None else "-"),
                ("volume", audio[4] if audio[4] is not None else "-"),
            ]
        )
        lines.append(f"[config] audio_options: {audio_kv}")

    return lines


def _run_download(
    manager: JobManager,
    job_id: str,
    url: str,
    dest: str,
    cut_start: str | None,
    cut_end: str | None,
    output_title: str | None = None,
    cuts: list | None = None,
    audio_fade: bool = False,
    audio_loudnorm: bool = False,
    audio_mute: bool = False,
    audio_bitrate: int | None = None,
    audio_volume: float | None = None,
    **encode_kwargs,
) -> None:
    manager.update(
        job_id,
        status=JobStatus.DOWNLOADING,
        error="",
        progress_phase="Preparing",
        progress_detail="",
    )
    try:
        site_cls = sites.validate_url(url)
        site = sites.create_site(
            url,
            savepath=dest,
            silence=True,
            cut_start=cut_start,
            cut_end=cut_end,
            cuts=cuts,
            **_audio_options(
                audio_fade=audio_fade,
                audio_loudnorm=audio_loudnorm,
                audio_mute=audio_mute,
                audio_bitrate=audio_bitrate,
                audio_volume=audio_volume,
            ),
            **_encode_options(**encode_kwargs),
        )
        if site is None or not site.is_url_vaildate():
            manager.update(
                job_id,
                status=JobStatus.FAILED,
                error="Could not resolve video metadata",
            )
            return

        try:
            _apply_output_title(site, output_title)
        except OSError as exc:
            manager.update(job_id, status=JobStatus.FAILED, error=str(exc))
            return

        manager.update(
            job_id,
            title=site.target_name() or "",
            site=_site_label(site_cls) if site_cls else "",
            thumbnail=getattr(site, "_imageUrl", None) or "",
            dest_folder=site.dest_folder() or dest,
        )

        def _on_log(message: str) -> None:
            stamp = _log_stamp()
            line = f"[{stamp}] {message}"
            manager.append_log(job_id, line)
            parsed = phase_from_log(message)
            if parsed:
                phase, detail = parsed
                manager.set_phase(job_id, phase, detail)

        def _on_phase(phase: str, detail: str = "") -> None:
            manager.set_phase(job_id, phase, detail)

        site._job_log = _on_log
        site._progress_phase = _on_phase
        _on_log("Preparing download…")
        for _config_line in _config_log_lines(site, output_title):
            _on_log(_config_line)
        stream_label = getattr(site, "_active_stream_label", None)
        if stream_label:
            _on_log(f"Using stream mirror: {stream_label}")
        if getattr(site, "_m3u8url", None):
            _on_log(f"HLS source: {site._m3u8url}")
        elif getattr(site, "_direct_url", None):
            _on_log("Direct MP4 source resolved")

        if getattr(site, "_direct_url", None):
            progress_unit = "bytes"
        elif getattr(site, "_m3u8url", None):
            progress_unit = "segments"
        else:
            progress_unit = ""

        def _on_progress(
            downloaded: int, total: int, speed: float, unit: str | None = None
        ) -> None:
            unit = unit or progress_unit
            phase = None
            detail = None
            job = manager.get(job_id)
            current_phase = job.progress_phase if job else ""
            current_detail = job.progress_detail if job else ""
            if unit == "segments" and total > 0:
                phase, detail = "Downloading", f"{downloaded}/{total} segments"
            elif unit == "bytes" and total > 0:
                if current_phase == "Encoding":
                    phase, detail = "Encoding", current_detail
                else:
                    phase, detail = "Downloading", "transfer"
            manager.set_progress(
                job_id,
                downloaded,
                total,
                speed,
                progress_unit=unit,
                progress_phase=phase,
                progress_detail=detail,
            )

        site._progress_callback = _on_progress
        # Keep the first start across pauses so the total includes
        # everything before a resume.
        current = manager.get(job_id)
        started = (
            current.started_at if current and current.started_at > 0 else time.time()
        )
        manager.update(job_id, progress_unit=progress_unit, started_at=started)

        with _active_lock:
            _active_downloads[job_id] = site
        try:
            if site.is_target_video_exist():
                output = site._get_video_savename()
                manager.update(
                    job_id,
                    status=JobStatus.COMPLETED,
                    output_file=output,
                    progress_pct=100.0,
                    downloaded=1,
                    total=1,
                    completed_at=time.time(),
                )
                return

            _on_log("Starting transfer…")
            site.start_download()
            if getattr(site, "_pause_job", False):
                _on_log("Download paused")
                manager.update(
                    job_id,
                    status=JobStatus.PAUSED,
                    speed=0.0,
                    progress_phase="Paused",
                    progress_detail="",
                )
                manager.notify_change()
                return

            output = (
                getattr(site, "_encoded_output_path", None)
                or site._get_video_savename()
            )
            if os.path.isfile(output):
                size = os.path.getsize(output)
                _on_log(f"Saving as {os.path.basename(output)}")
                _on_log(f"Complete: {output}")
                manager.update(
                    job_id,
                    status=JobStatus.COMPLETED,
                    output_file=output,
                    progress_pct=100.0,
                    downloaded=size,
                    total=size,
                    completed_at=time.time(),
                )
            elif not getattr(site, "_cancel_job", False):
                manager.update(
                    job_id,
                    status=JobStatus.FAILED,
                    error="Download finished but output file was not found",
                )
        finally:
            with _active_lock:
                _active_downloads.pop(job_id, None)
    except Exception as exc:
        job = manager.get(job_id)
        if job is not None and job.status == JobStatus.PAUSED:
            return
        manager.append_log(job_id, f"[{_log_stamp()}] Error: {exc}")
        manager.update(job_id, status=JobStatus.FAILED, error=str(exc))


def start_download(
    manager: JobManager,
    url: str,
    dest_folder: str | None = None,
    cut_start: str | None = None,
    cut_end: str | None = None,
    cuts: list | None = None,
    output_title: str | None = None,
    audio_fade: bool = False,
    audio_loudnorm: bool = False,
    audio_mute: bool = False,
    audio_bitrate: int | None = None,
    audio_volume: float | None = None,
    **encode_kwargs,
) -> Job:
    """Queue a download and return its job record."""
    url = (url or "").strip()
    job = manager.create(url)
    dest = validate_dest_folder(dest_folder)
    os.makedirs(dest, exist_ok=True)
    cut_start = _optional_time(cut_start)
    cut_end = _optional_time(cut_end)
    output_title = _optional_text(output_title)
    _job_params[job.id] = {
        "url": url,
        "dest": dest,
        "cut_start": cut_start,
        "cut_end": cut_end,
        "cuts": cuts,
        "output_title": output_title,
        **_audio_options(
            audio_fade=audio_fade,
            audio_loudnorm=audio_loudnorm,
            audio_mute=audio_mute,
            audio_bitrate=audio_bitrate,
            audio_volume=audio_volume,
        ),
        **_encode_options(**encode_kwargs),
    }

    thread = threading.Thread(
        target=_run_download,
        args=(manager, job.id, url, dest, cut_start, cut_end, output_title, cuts),
        kwargs={
            **_audio_options(
                audio_fade=audio_fade,
                audio_loudnorm=audio_loudnorm,
                audio_mute=audio_mute,
                audio_bitrate=audio_bitrate,
                audio_volume=audio_volume,
            ),
            **_encode_options(**encode_kwargs),
        },
        name=f"jav-web-{job.id}",
        daemon=True,
    )
    thread.start()
    return job


def _resume_params(job_id: str) -> dict | None:
    params = _job_params.get(job_id)
    if isinstance(params, dict) and params.get("url"):
        return params
    _jobs, params_by_id = _job_store().load()
    params = params_by_id.get(job_id)
    if isinstance(params, dict) and params.get("url"):
        _job_params[job_id] = params
        return params
    return None


def pause_download(manager: JobManager, job_id: str) -> bool:
    """Pause an active download without deleting partial files."""
    job = manager.get(job_id)
    if job is None:
        return False
    if job.status == JobStatus.PAUSED:
        return True
    if job.status != JobStatus.DOWNLOADING:
        return False

    with _active_lock:
        site = _active_downloads.get(job_id)
    if site is not None:
        site.pause_download()
    manager.update(
        job_id,
        status=JobStatus.PAUSED,
        speed=0.0,
        progress_phase="Paused",
        progress_detail="",
    )
    manager.notify_change()
    return True


def resume_download(manager: JobManager, job_id: str) -> bool:
    """Continue a paused download from partial files when possible."""
    with _active_lock:
        if job_id in _active_downloads:
            return False

    job = manager.get(job_id)
    if job is None:
        return False
    if job.status == JobStatus.DOWNLOADING:
        return False
    if job.status != JobStatus.PAUSED:
        return False

    params = _resume_params(job_id)
    if params is None:
        return False

    manager.update(
        job_id,
        status=JobStatus.DOWNLOADING,
        speed=0.0,
        error="",
        progress_phase="Downloading",
    )
    thread = threading.Thread(
        target=_run_download,
        args=(
            manager,
            job_id,
            params["url"],
            params["dest"],
            params.get("cut_start"),
            params.get("cut_end"),
            params.get("output_title"),
            params.get("cuts"),
        ),
        kwargs={
            **_audio_options_from_mapping(params),
            **_encode_options_from_mapping(params),
        },
        name=f"jav-web-{job_id}-resume",
        daemon=True,
    )
    thread.start()
    return True


def cancel_download(manager: JobManager, job_id: str) -> bool:
    """Stop an in-flight download and discard partial files."""
    with _active_lock:
        site = _active_downloads.get(job_id)
    if site is not None:
        site.cancel_download(cleanup=True)
        manager.update(
            job_id,
            status=JobStatus.FAILED,
            error="Download cancelled",
            speed=0.0,
            progress_pct=0.0,
            downloaded=0,
            total=0,
            progress_phase="",
            progress_detail="",
        )
        _job_params.pop(job_id, None)
        _job_store().delete(job_id)
        manager.notify_change()
        return True
    job = manager.get(job_id)
    if job is not None and job.status in (
        JobStatus.DOWNLOADING,
        JobStatus.PAUSED,
        JobStatus.PENDING,
    ):
        manager.update(
            job_id,
            status=JobStatus.FAILED,
            error="Download cancelled",
            speed=0.0,
            progress_pct=0.0,
            downloaded=0,
            total=0,
            progress_phase="",
            progress_detail="",
        )
        _job_params.pop(job_id, None)
        _job_store().delete(job_id)
        manager.notify_change()
        return True
    return False
