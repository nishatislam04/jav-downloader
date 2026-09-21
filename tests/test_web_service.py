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


def test_pause_download_is_idempotent_when_already_paused():
    manager = JobManager()
    job = manager.create("https://example.test/video")
    manager.update(job.id, status=JobStatus.PAUSED)

    assert service.pause_download(manager, job.id) is True


def test_pause_download_marks_paused_when_worker_already_gone():
    manager = JobManager()
    job = manager.create("https://example.test/video")
    manager.update(job.id, status=JobStatus.DOWNLOADING)

    assert service.pause_download(manager, job.id) is True
    assert manager.get(job.id).status == JobStatus.PAUSED


def test_resume_download_rejects_active_worker():
    manager = JobManager()
    job = manager.create("https://example.test/video")
    manager.update(job.id, status=JobStatus.PAUSED)
    service._job_params[job.id] = {
        "url": job.url,
        "dest": "/tmp",
        "cut_start": None,
        "cut_end": None,
    }
    service._active_downloads[job.id] = FakeSite()

    assert service.resume_download(manager, job.id) is False
    service._active_downloads.pop(job.id, None)


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


def _config_site(**attrs):
    class _Site:
        def dest_folder(self):
            return attrs.get("dest", "/tmp/dl")

    site = _Site()
    for key, value in attrs.items():
        if key != "dest":
            setattr(site, key, value)
    return site


def test_config_log_lines_defaults():
    site = _config_site(_max_workers=8, _filename_mode="original")
    lines = service._config_log_lines(site)

    assert "[config] dest: /tmp/dl" in lines
    assert any(line.startswith("[config] resolution: ") for line in lines)
    assert "[config] filename_mode: original" in lines
    assert "[config] workers: 8" in lines
    assert "[config] encode: off" in lines
    assert not any(line.startswith("[config] cuts:") for line in lines)
    assert not any(line.startswith("[config] audio_options:") for line in lines)


def test_config_log_lines_full_encode_audio_cuts():
    site = _config_site(
        _encode_enabled=True,
        _encode_codec="h264",
        _encode_crf=23,
        _encode_preset="veryfast",
        _encode_threads=4,
        _encode_max_height=1080,
        _encode_output_mode="remux",
        _cut_ranges=[(60.0, 120.0), (300.0, None)],
        _audio_mute=True,
        _audio_fade=False,
        _audio_loudnorm=True,
        _audio_bitrate=128,
        _audio_volume=1.5,
    )
    lines = service._config_log_lines(site, output_title="My Title")

    assert "[config] encode: on" in lines
    assert "[config] encode_options: codec=h264, crf=23, preset=veryfast, threads=4, max_height=1080, output_mode=remux" in lines
    assert not any(line.startswith("[config] encode_hw:") for line in lines)
    assert "[config] cuts: 0:01:00-0:02:00, 0:05:00-end" in lines
    assert "[config] output_title: My Title" in lines
    assert "[config] audio_options: mute=on, fade=off, loudnorm=on, bitrate=128, volume=1.5" in lines


def test_config_log_lines_hardware_engine_details():
    site = _config_site(
        _encode_enabled=True,
        _encode_codec="h264",
        _encode_engine="mediacodec",
        _encode_hardware_bitrate_kbps=4000,
        _encode_hardware_gop=240,
        _encode_hardware_bitrate_mode="vbr",
    )
    lines = service._config_log_lines(site)

    hw = next(line for line in lines if line.startswith("[config] encode_hw:"))
    assert "engine=mediacodec" in hw
    assert "bitrate_kbps=4000" in hw
    assert "gop=240" in hw
    assert "bitrate_mode=vbr" in hw
