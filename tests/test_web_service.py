import sys
import types

import pytest


def _stub(name, factory=None):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory() if factory else types.ModuleType(name)


_stub("cloudscraper")
_stub("m3u8")

from jav_downloader.web import service  # noqa: E402
from jav_downloader.web.jobs import Job, JobManager, JobStatus  # noqa: E402


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
    job = manager.create("https://example.test/video")
    manager.update(job.id, status=JobStatus.DOWNLOADING)
    fake = FakeSite()
    service._active_downloads[job.id] = fake

    assert service.pause_download(manager, job.id) is True
    assert fake.paused is True
    assert manager.get(job.id).status == JobStatus.PAUSED


def test_resume_download_requires_paused_job():
    manager = JobManager()
    job = manager.create("https://example.test/video")
    service._job_params[job.id] = {
        "url": job.url,
        "dest": "/tmp",
        "cut_start": None,
        "cut_end": None,
    }

    assert service.resume_download(manager, job.id) is False

    manager.update(job.id, status=JobStatus.PAUSED)
    assert service.resume_download(manager, job.id) is True


def test_pause_download_is_idempotent_when_worker_gone():
    manager = JobManager()
    job = manager.create("https://example.test/video")
    manager.update(job.id, status=JobStatus.PAUSED)

    # No site registered (worker already unwound) — pause still succeeds.
    assert service.pause_download(manager, job.id) is True


def test_restore_saved_jobs_registers_params():
    manager = JobManager()
    service._job_params.clear()
    paused = Job(
        id="restored",
        url="https://example.test/video",
        status=JobStatus.PAUSED,
        dest_folder="/tmp/jav",
    )

    class FakeStore:
        def load(self):
            return [paused], {"restored": {"url": paused.url, "dest": "/tmp/jav"}}

    original = service._job_store_instance
    service._job_store_instance = FakeStore()
    try:
        assert service.restore_saved_jobs(manager) == 1
    finally:
        service._job_store_instance = original

    assert manager.get("restored") is paused
    assert service._job_params["restored"]["dest"] == "/tmp/jav"


def test_cancel_download_clears_saved_params():
    manager = JobManager()
    job = manager.create("https://example.test/video")
    manager.update(job.id, status=JobStatus.PAUSED)
    service._job_params[job.id] = {
        "url": job.url,
        "dest": "/tmp",
        "cut_start": None,
        "cut_end": None,
    }

    assert service.cancel_download(manager, job.id) is True
    assert job.id not in service._job_params
    assert manager.get(job.id).status == JobStatus.FAILED


def test_job_elapsed_sec_zero_until_completed():
    manager = JobManager()
    job = manager.create("https://example.test/video")

    assert job.elapsed_sec == 0.0
    assert job.to_dict()["elapsed_sec"] == 0.0


def test_job_elapsed_sec_uses_started_at_when_present():
    job = Job(id="x", url="https://example.test/video")
    job.created_at = 100.0
    job.started_at = 110.0
    job.completed_at = 150.0

    assert job.elapsed_sec == pytest.approx(40.0)
    assert job.to_dict()["elapsed_sec"] == pytest.approx(40.0)


def test_job_elapsed_sec_falls_back_to_created_at():
    job = Job(id="x", url="https://example.test/video")
    job.created_at = 100.0
    job.completed_at = 130.5

    assert job.elapsed_sec == pytest.approx(30.5)
