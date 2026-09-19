import sys
import types

import pytest


def _stub(name, factory=None):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory() if factory else types.ModuleType(name)


_stub('cloudscraper')
_stub('m3u8')

from jav_downloader.web.jobs import JobManager, JobStatus
from jav_downloader.web import service


class FakeSite:
    def __init__(self):
        self._pause_job = False
        self._cancel_job = False
        self.paused = False
        self.cancelled = False

    def pause_download(self):
        self.paused = True
        self._pause_job = True

    def cancel_download(self, cleanup=True):
        self.cancelled = True
        self._cancel_job = True


def test_pause_download_marks_job_paused():
    manager = JobManager()
    job = manager.create('https://example.test/video')
    manager.update(job.id, status=JobStatus.DOWNLOADING)
    fake = FakeSite()
    service._active_downloads[job.id] = fake

    assert service.pause_download(manager, job.id) is True
    assert fake.paused is True
    assert manager.get(job.id).status == JobStatus.PAUSED


def test_resume_download_requires_paused_job():
    manager = JobManager()
    job = manager.create('https://example.test/video')
    service._job_params[job.id] = {
        'url': job.url,
        'dest': '/tmp',
        'cut_start': None,
        'cut_end': None,
    }

    assert service.resume_download(manager, job.id) is False

    manager.update(job.id, status=JobStatus.PAUSED)
    assert service.resume_download(manager, job.id) is True


def test_cancel_download_clears_saved_params():
    manager = JobManager()
    job = manager.create('https://example.test/video')
    manager.update(job.id, status=JobStatus.PAUSED)
    service._job_params[job.id] = {
        'url': job.url,
        'dest': '/tmp',
        'cut_start': None,
        'cut_end': None,
    }

    assert service.cancel_download(manager, job.id) is True
    assert job.id not in service._job_params
    assert manager.get(job.id).status == JobStatus.FAILED
