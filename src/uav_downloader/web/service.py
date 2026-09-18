"""Resolve URLs and run background downloads for the web UI."""

from __future__ import annotations

import os
import threading

from uav_downloader import sites
from uav_downloader.web.jobs import Job, JobManager, JobStatus
from uav_downloader.web.paths import default_download_dir

_active_downloads: dict[str, object] = {}
_active_lock = threading.Lock()
_job_params: dict[str, dict] = {}


def _site_label(site_cls) -> str:
    return getattr(site_cls, 'direct_site_name', None) or site_cls.__name__


def _optional_time(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_url(
        url: str,
        dest_folder: str | None = None,
        cut_start: str | None = None,
        cut_end: str | None = None) -> dict:
    """Collect metadata for a supported URL without starting a download."""
    url = (url or '').strip()
    if not url:
        return {'ok': False, 'error': 'URL is required'}

    site_cls = sites.validate_url(url)
    if site_cls is None:
        return {'ok': False, 'error': 'Unsupported URL'}

    dest = dest_folder or default_download_dir()
    os.makedirs(dest, exist_ok=True)

    try:
        site = sites.create_site(
            url,
            savepath=dest,
            silence=True,
            cut_start=_optional_time(cut_start),
            cut_end=_optional_time(cut_end),
        )
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}

    if site is None:
        return {'ok': False, 'error': 'Unsupported URL'}

    if not site.is_url_vaildate():
        message = getattr(site, '_last_error', None)
        return {
            'ok': False,
            'error': str(message) if message else 'Could not resolve video metadata',
        }

    return {
        'ok': True,
        'url': url,
        'site': _site_label(site_cls),
        'title': site.target_name() or '',
        'thumbnail': getattr(site, '_imageUrl', None) or '',
        'dest_folder': site.dest_folder() or dest,
        'exists': site.is_target_video_exist(),
        'duration_sec': getattr(site, '_duration_sec', None),
        'quality': getattr(site, '_quality_label', None) or '',
        'views': getattr(site, '_views_label', None) or '',
        'uploader': getattr(site, '_uploader', None) or '',
    }


def _run_download(
        manager: JobManager,
        job_id: str,
        url: str,
        dest: str,
        cut_start: str | None,
        cut_end: str | None) -> None:
    manager.update(job_id, status=JobStatus.DOWNLOADING, error='')
    try:
        site_cls = sites.validate_url(url)
        site = sites.create_site(
            url,
            savepath=dest,
            silence=True,
            cut_start=cut_start,
            cut_end=cut_end,
        )
        if site is None or not site.is_url_vaildate():
            manager.update(
                job_id,
                status=JobStatus.FAILED,
                error='Could not resolve video metadata',
            )
            return

        manager.update(
            job_id,
            title=site.target_name() or '',
            site=_site_label(site_cls) if site_cls else '',
            thumbnail=getattr(site, '_imageUrl', None) or '',
            dest_folder=site.dest_folder() or dest,
        )

        if getattr(site, '_direct_url', None):
            progress_unit = 'bytes'
        elif getattr(site, '_m3u8url', None):
            progress_unit = 'segments'
        else:
            progress_unit = ''

        def _on_progress(downloaded: int, total: int, speed: float) -> None:
            manager.set_progress(
                job_id,
                downloaded,
                total,
                speed,
                progress_unit=progress_unit,
            )

        site._progress_callback = _on_progress
        manager.update(job_id, progress_unit=progress_unit)

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
                )
                return

            site.start_download()
            if getattr(site, '_pause_job', False):
                manager.update(
                    job_id,
                    status=JobStatus.PAUSED,
                    speed=0.0,
                )
                return

            output = site._get_video_savename()
            if os.path.isfile(output):
                size = os.path.getsize(output)
                manager.update(
                    job_id,
                    status=JobStatus.COMPLETED,
                    output_file=output,
                    progress_pct=100.0,
                    downloaded=size,
                    total=size,
                )
            elif not getattr(site, '_cancel_job', False):
                manager.update(
                    job_id,
                    status=JobStatus.FAILED,
                    error='Download finished but output file was not found',
                )
        finally:
            with _active_lock:
                _active_downloads.pop(job_id, None)
    except Exception as exc:
        job = manager.get(job_id)
        if job is not None and job.status == JobStatus.PAUSED:
            return
        manager.update(job_id, status=JobStatus.FAILED, error=str(exc))


def start_download(
        manager: JobManager,
        url: str,
        dest_folder: str | None = None,
        cut_start: str | None = None,
        cut_end: str | None = None) -> Job:
    """Queue a download and return its job record."""
    url = (url or '').strip()
    job = manager.create(url)
    dest = dest_folder or default_download_dir()
    os.makedirs(dest, exist_ok=True)
    cut_start = _optional_time(cut_start)
    cut_end = _optional_time(cut_end)
    _job_params[job.id] = {
        'url': url,
        'dest': dest,
        'cut_start': cut_start,
        'cut_end': cut_end,
    }

    thread = threading.Thread(
        target=_run_download,
        args=(manager, job.id, url, dest, cut_start, cut_end),
        name=f'uav-web-{job.id}',
        daemon=True,
    )
    thread.start()
    return job


def pause_download(manager: JobManager, job_id: str) -> bool:
    """Pause an active download without deleting partial files."""
    with _active_lock:
        site = _active_downloads.get(job_id)
    if site is None:
        return False
    site.pause_download()
    manager.update(job_id, status=JobStatus.PAUSED, speed=0.0)
    return True


def resume_download(manager: JobManager, job_id: str) -> bool:
    """Continue a paused download from partial files when possible."""
    job = manager.get(job_id)
    if job is None or job.status != JobStatus.PAUSED:
        return False
    params = _job_params.get(job_id)
    if params is None:
        return False
    thread = threading.Thread(
        target=_run_download,
        args=(
            manager,
            job_id,
            params['url'],
            params['dest'],
            params.get('cut_start'),
            params.get('cut_end'),
        ),
        name=f'uav-web-{job_id}-resume',
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
            error='Download cancelled',
            speed=0.0,
        )
        _job_params.pop(job_id, None)
        return True
    job = manager.get(job_id)
    if job is not None and job.status in (
            JobStatus.DOWNLOADING, JobStatus.PAUSED, JobStatus.PENDING):
        manager.update(
            job_id,
            status=JobStatus.FAILED,
            error='Download cancelled',
            speed=0.0,
        )
        _job_params.pop(job_id, None)
        return True
    return False
