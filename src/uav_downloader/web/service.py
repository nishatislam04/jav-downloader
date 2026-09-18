"""Resolve URLs and run background downloads for the web UI."""

from __future__ import annotations

import os
import threading

from uav_downloader import sites
from uav_downloader.web.jobs import Job, JobManager, JobStatus
from uav_downloader.web.paths import default_download_dir


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
    }


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

    def _run() -> None:
        manager.update(job.id, status=JobStatus.DOWNLOADING, dest_folder=dest)
        try:
            site_cls = sites.validate_url(url)
            site = sites.create_site(
                url,
                savepath=dest,
                silence=True,
                cut_start=_optional_time(cut_start),
                cut_end=_optional_time(cut_end),
            )
            if site is None or not site.is_url_vaildate():
                manager.update(
                    job.id,
                    status=JobStatus.FAILED,
                    error='Could not resolve video metadata',
                )
                return

            manager.update(
                job.id,
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
                    job.id,
                    downloaded,
                    total,
                    speed,
                    progress_unit=progress_unit,
                )

            site._progress_callback = _on_progress
            manager.update(job.id, progress_unit=progress_unit)

            if site.is_target_video_exist():
                output = site._get_video_savename()
                manager.update(
                    job.id,
                    status=JobStatus.COMPLETED,
                    output_file=output,
                    progress_pct=100.0,
                    downloaded=1,
                    total=1,
                )
                return

            site.start_download()
            output = site._get_video_savename()
            if os.path.isfile(output):
                manager.update(
                    job.id,
                    status=JobStatus.COMPLETED,
                    output_file=output,
                    progress_pct=100.0,
                )
            else:
                manager.update(
                    job.id,
                    status=JobStatus.FAILED,
                    error='Download finished but output file was not found',
                )
        except Exception as exc:
            manager.update(job.id, status=JobStatus.FAILED, error=str(exc))

    thread = threading.Thread(target=_run, name=f'uav-web-{job.id}', daemon=True)
    thread.start()
    return job
