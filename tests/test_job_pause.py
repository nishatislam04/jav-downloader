from jav_downloader.web.jobs import Job, JobManager, JobStatus


def test_set_progress_does_not_clobber_paused_status():
    manager = JobManager()
    job = manager.create("https://example.test/video")
    manager.update(job.id, status=JobStatus.PAUSED, speed=0.0)

    manager.set_progress(job.id, 20, 60, 1024.0, progress_unit="segments")

    updated = manager.get(job.id)
    assert updated.status == JobStatus.PAUSED
    assert updated.downloaded == 20
    assert updated.total == 60
    assert updated.speed == 0.0


def test_set_progress_sets_downloading_when_active():
    manager = JobManager()
    job = manager.create("https://example.test/video")
    manager.update(job.id, status=JobStatus.DOWNLOADING)

    manager.set_progress(job.id, 5, 10, 512.0)

    updated = manager.get(job.id)
    assert updated.status == JobStatus.DOWNLOADING
    assert updated.speed == 512.0
