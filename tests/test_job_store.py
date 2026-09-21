import json
import sqlite3
from pathlib import Path

from jav_downloader.web.job_store import JobStore, legacy_json_path, store_path
from jav_downloader.web.jobs import Job, JobStatus


def test_save_writes_only_paused_jobs_with_params(tmp_path):
    store = JobStore(str(tmp_path))
    paused = Job(id="p", url="https://example.test/a", status=JobStatus.PAUSED)
    done = Job(id="d", url="https://example.test/b", status=JobStatus.COMPLETED)
    store.save([paused, done], {"p": {"url": paused.url, "dest": "/tmp"}})

    conn = sqlite3.connect(store_path(str(tmp_path)))
    rows = conn.execute("SELECT id, params_json FROM jobs").fetchall()
    conn.close()
    assert rows == [("p", json.dumps({"url": paused.url, "dest": "/tmp"}))]


def test_save_skips_write_when_payload_unchanged(tmp_path):
    store = JobStore(str(tmp_path))
    job = Job(id="p", url="https://example.test/a", status=JobStatus.PAUSED)
    params = {"url": job.url, "dest": "/tmp"}
    store.save([job], {"p": params})
    db_path = Path(store_path(str(tmp_path)))
    first_mtime = db_path.stat().st_mtime_ns
    store.save([job], {"p": params})
    assert db_path.stat().st_mtime_ns == first_mtime


def test_load_restores_jobs_and_params(tmp_path):
    store = JobStore(str(tmp_path))
    job = Job(
        id="p",
        url="https://example.test/a",
        status=JobStatus.PAUSED,
        title="T",
        progress_pct=60.4,
        log=["[x] hi"],
    )
    store.save([job], {"p": {"url": job.url, "dest": "/tmp"}})

    jobs, params = store.load()
    assert len(jobs) == 1
    assert jobs[0].id == "p"
    assert jobs[0].status == JobStatus.PAUSED
    assert jobs[0].progress_pct == 60.4
    assert jobs[0].log == ["[x] hi"]
    assert params["p"]["dest"] == "/tmp"


def test_load_handles_missing_or_bad_files(tmp_path):
    store = JobStore(str(tmp_path))
    assert store.load() == ([], {})


def test_load_coerces_terminal_status_to_paused(tmp_path):
    store = JobStore(str(tmp_path))
    conn = sqlite3.connect(store.path)
    conn.execute(
        "INSERT INTO jobs (id, url, status, params_json) VALUES (?, ?, ?, ?)",
        ("x", "u", "completed", "{}"),
    )
    conn.commit()
    conn.close()

    jobs, _params = store.load()
    assert jobs[0].status == JobStatus.PAUSED


def test_imports_legacy_json_once(tmp_path):
    legacy = Path(legacy_json_path(str(tmp_path)))
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "jobs": [
                    {
                        "id": "legacy",
                        "url": "https://example.test/a",
                        "status": "paused",
                        "params": {"url": "https://example.test/a", "dest": "/tmp"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    store = JobStore(str(tmp_path))
    jobs, params = store.load()
    assert jobs[0].id == "legacy"
    assert params["legacy"]["dest"] == "/tmp"


def test_delete_removes_job(tmp_path):
    store = JobStore(str(tmp_path))
    job = Job(id="p", url="https://example.test/a", status=JobStatus.PAUSED)
    store.save([job], {"p": {"url": job.url, "dest": "/tmp"}})
    store.delete("p")
    assert store.load() == ([], {})
