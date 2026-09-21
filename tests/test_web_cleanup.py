import sys
import types


def _stub(name, factory=None):
    try:
        __import__(name)
    except ImportError:
        sys.modules[name] = factory() if factory else types.ModuleType(name)


_stub("cloudscraper")
_stub("m3u8")

from jav_downloader.web import cleanup  # noqa: E402
from jav_downloader.web.jobs import JobManager, JobStatus  # noqa: E402


def test_sweep_removes_temp_files_and_part(tmp_path):
    (tmp_path / "jav-encode-abc.mp4").write_bytes(b"x" * 10)
    (tmp_path / "jav-audio-def.mp4").write_bytes(b"x" * 5)
    (tmp_path / "jav-cut-ghi.mp4").write_bytes(b"x" * 3)
    (tmp_path / "video.mp4.part").write_bytes(b"x" * 7)
    keep = tmp_path / "finished video.mp4"
    keep.write_bytes(b"x" * 100)

    result = cleanup.sweep_dest_folder(str(tmp_path))

    assert result["ok"] is True
    assert result["removed_files"] == 4
    assert result["freed_bytes"] == 25
    assert keep.exists()


def test_sweep_removes_workdirs_and_segment_dirs(tmp_path):
    remux = tmp_path / "jav-remux-xyz"
    remux.mkdir()
    (remux / "merged.ts").write_bytes(b"x" * 50)

    segdir = tmp_path / "Some Video Name"
    segdir.mkdir()
    for i in range(3):
        (segdir / f"{i:06d}.mp4").write_bytes(b"x")

    mixed = tmp_path / "user album"
    mixed.mkdir()
    (mixed / "000001.mp4").write_bytes(b"x")
    (mixed / "cover.jpg").write_bytes(b"x")

    result = cleanup.sweep_dest_folder(str(tmp_path))

    assert result["ok"] is True
    assert result["removed_dirs"] == 2
    assert not remux.exists()
    assert not segdir.exists()
    assert mixed.exists(), "mixed-content dirs must never be deleted"


def test_sweep_keeps_symlink_escape(tmp_path, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "jav-encode-evil.mp4").write_bytes(b"x")
    link = tmp_path / "jav-encode-link.mp4"
    link.symlink_to(outside / "jav-encode-evil.mp4")

    result = cleanup.sweep_dest_folder(str(tmp_path))

    assert result["ok"] is True
    assert (outside / "jav-encode-evil.mp4").exists(), (
        "symlinked target outside root must not be deleted"
    )


def test_sweep_removes_merged_ts_at_top_level(tmp_path):
    (tmp_path / "merged.ts").write_bytes(b"x" * 20)
    keep = tmp_path / "finished.mp4"
    keep.write_bytes(b"x" * 10)

    result = cleanup.sweep_dest_folder(str(tmp_path))

    assert result["ok"] is True
    assert result["removed_files"] == 1
    assert not (tmp_path / "merged.ts").exists()
    assert keep.exists()


def test_sweep_missing_dir_reports_error(tmp_path):
    result = cleanup.sweep_dest_folder(str(tmp_path / "nope"))

    assert result["ok"] is False
    assert "does not exist" in result["error"]


def test_cleanup_job_requires_stopped_job():
    manager = JobManager()
    job = manager.create("https://example.test/video")
    manager.update(job.id, status=JobStatus.DOWNLOADING, dest_folder="/tmp/somewhere")

    result = cleanup.cleanup_job(manager, job.id, wait_timeout=0.1)

    assert result["ok"] is False
    assert "shutting down" in result["error"]


def test_cleanup_job_sweeps_completed_job_folder(tmp_path):
    manager = JobManager()
    job = manager.create("https://example.test/video")
    manager.update(job.id, status=JobStatus.COMPLETED, dest_folder=str(tmp_path))
    (tmp_path / "jav-encode-orphan.mp4").write_bytes(b"x" * 4)

    result = cleanup.cleanup_job(manager, job.id)

    assert result["ok"] is True
    assert result["removed_files"] == 1
    assert not (tmp_path / "jav-encode-orphan.mp4").exists()
