import json

from jav_downloader.web.job_store import JobStore
from jav_downloader.web.jobs import Job, JobStatus


def _write(tmp_path, payload):
    path = tmp_path / ".jav-downloader-jobs.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_save_writes_only_paused_jobs_with_params(tmp_path):
    store = JobStore(str(tmp_path))
    paused = Job(id="p", url="https://example.test/a", status=JobStatus.PAUSED)
    done = Job(id="d", url="https://example.test/b", status=JobStatus.COMPLETED)
    store.save([paused, done], {"p": {"url": paused.url, "dest": "/tmp"}})

    payload = json.loads((tmp_path / ".jav-downloader-jobs.json").read_text())
    assert [rec["id"] for rec in payload["jobs"]] == ["p"]
    assert payload["jobs"][0]["params"]["dest"] == "/tmp"


def test_save_skips_write_when_payload_unchanged(tmp_path):
    store = JobStore(str(tmp_path))
    job = Job(id="p", url="https://example.test/a", status=JobStatus.PAUSED)
    store.save([job], {})
    first_mtime = (tmp_path / ".jav-downloader-jobs.json").stat().st_mtime_ns
    store.save([job], {})
    assert (tmp_path / ".jav-downloader-jobs.json").stat().st_mtime_ns == first_mtime


def test_load_restores_jobs_and_params(tmp_path):
    path = _write(tmp_path, {
        "version": 1,
        "jobs": [{
            "id": "p",
            "url": "https://example.test/a",
            "status": "paused",
            "title": "T",
            "progress_pct": 60.4,
            "log": ["[x] hi"],
            "params": {"url": "https://example.test/a", "dest": "/tmp"},
        }],
    })
    store = JobStore(str(tmp_path))
    jobs, params = store.load()
    assert len(jobs) == 1
    assert jobs[0].id == "p"
    assert jobs[0].status == JobStatus.PAUSED
    assert jobs[0].progress_pct == 60.4
    assert params["p"]["dest"] == "/tmp"


def test_load_handles_missing_or_bad_files(tmp_path):
    store = JobStore(str(tmp_path))
    assert store.load() == ([], {})

    _write(tmp_path, {"version": 1})
    assert store.load() == ([], {})

    (tmp_path / ".jav-downloader-jobs.json").write_text("not json")
    assert store.load() == ([], {})


def test_load_coerces_terminal_status_to_paused(tmp_path):
    _write(tmp_path, {
        "version": 1,
        "jobs": [{"id": "x", "url": "u", "status": "completed"}],
    })
    jobs, _params = JobStore(str(tmp_path)).load()
    assert jobs[0].status == JobStatus.PAUSED
