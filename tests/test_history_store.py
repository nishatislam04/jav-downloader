import json
import sqlite3

from jav_downloader.web.history_store import HistoryStore, history_db_path
from jav_downloader.web.jobs import Job, JobStatus


def test_upsert_and_list(tmp_path):
    store = HistoryStore(appdata=tmp_path)
    job = Job(id="a", url="https://example.test/v", status=JobStatus.DOWNLOADING)
    job.title = "T"
    job.log = ["line"]
    store.upsert_job(job, {"url": job.url})

    entries = store.list_records()
    assert len(entries) == 1
    assert entries[0]["id"] == "a"
    assert entries[0]["title"] == "T"
    assert entries[0]["status"] == "downloading"

    full = store.get_record("a")
    assert full is not None
    assert full["log"] == ["line"]
    assert full["meta"]["url"] == job.url


def test_throttle_skips_rapid_updates(tmp_path, monkeypatch):
    store = HistoryStore(appdata=tmp_path)
    job = Job(id="b", url="https://example.test/b", status=JobStatus.DOWNLOADING)
    times = iter([100.0, 100.5])
    monkeypatch.setattr(
        "jav_downloader.web.history_store.time.time", lambda: next(times)
    )
    store.upsert_jobs_throttled([job])
    conn = sqlite3.connect(store.path)
    first = conn.execute(
        "SELECT progress_pct FROM download_records WHERE id = 'b'"
    ).fetchone()[0]
    conn.close()

    job.progress_pct = 50.0
    store.upsert_jobs_throttled([job])

    conn = sqlite3.connect(store.path)
    second = conn.execute(
        "SELECT progress_pct FROM download_records WHERE id = 'b'"
    ).fetchone()[0]
    conn.close()
    assert second == first

    job.progress_pct = 75.0
    times = iter([103.0])
    monkeypatch.setattr(
        "jav_downloader.web.history_store.time.time", lambda: next(times)
    )
    store.upsert_jobs_throttled([job])
    conn = sqlite3.connect(store.path)
    third = conn.execute(
        "SELECT progress_pct FROM download_records WHERE id = 'b'"
    ).fetchone()[0]
    conn.close()
    assert third == 75.0


def test_terminal_status_always_flushes(tmp_path, monkeypatch):
    store = HistoryStore(appdata=tmp_path)
    job = Job(id="c", url="https://example.test/c", status=JobStatus.FAILED)
    job.error = "nope"
    times = iter([200.0, 200.1])
    monkeypatch.setattr(
        "jav_downloader.web.history_store.time.time", lambda: next(times)
    )
    store.upsert_jobs_throttled([job])
    assert store.get_record("c")["error"] == "nope"


def test_delete_and_clear(tmp_path):
    store = HistoryStore(appdata=tmp_path)
    store.upsert_job(Job(id="1", url="u1", status=JobStatus.COMPLETED))
    store.upsert_job(Job(id="2", url="u2", status=JobStatus.FAILED))
    assert store.delete("1")
    assert len(store.list_records()) == 1
    store.clear_all()
    assert store.list_records() == []


def test_import_menu_entries(tmp_path):
    store = HistoryStore(appdata=tmp_path)
    count = store.import_menu_entries(
        [
            {
                "id": "legacy",
                "url": "https://example.test/old",
                "title": "Old",
                "thumbnail": "https://img/t.jpg",
                "downloadedAt": 1_700_000_000_000,
            }
        ]
    )
    assert count == 1
    row = store.get_record("legacy")
    assert row["status"] == "completed"
    assert row["title"] == "Old"


def test_history_db_path_under_appdata(tmp_path):
    path = history_db_path(tmp_path)
    assert path.endswith("history.sqlite")
    assert "JAV Downloader" in path or str(tmp_path) in path
