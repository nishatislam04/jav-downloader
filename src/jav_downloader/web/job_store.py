"""Persist paused jobs so Resume works across server restarts.

Uses SQLite beside the download folder for atomic writes. Only paused jobs
with resume params are stored. A legacy JSON file is imported once on first
open, then left in place as a backup.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading

from jav_downloader.web.jobs import Job, JobStatus

_JOB_FIELDS = (
    "id",
    "url",
    "status",
    "title",
    "site",
    "thumbnail",
    "dest_folder",
    "output_file",
    "downloaded",
    "total",
    "progress_pct",
    "progress_unit",
    "progress_phase",
    "progress_detail",
    "error",
    "log",
    "created_at",
    "started_at",
    "completed_at",
    "updated_at",
)

_RESUMABLE_STATUSES = (JobStatus.PAUSED,)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    site TEXT NOT NULL DEFAULT '',
    thumbnail TEXT NOT NULL DEFAULT '',
    dest_folder TEXT NOT NULL DEFAULT '',
    output_file TEXT NOT NULL DEFAULT '',
    downloaded INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    progress_pct REAL NOT NULL DEFAULT 0,
    progress_unit TEXT NOT NULL DEFAULT '',
    progress_phase TEXT NOT NULL DEFAULT '',
    progress_detail TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    log_json TEXT NOT NULL DEFAULT '[]',
    created_at REAL NOT NULL DEFAULT 0,
    started_at REAL NOT NULL DEFAULT 0,
    completed_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0,
    params_json TEXT NOT NULL DEFAULT ''
);
"""


def store_path(dest_folder: str) -> str:
    """SQLite file lives beside the downloads so it survives restarts."""
    return os.path.join(dest_folder or "", ".jav-downloader-jobs.sqlite")


def legacy_json_path(dest_folder: str) -> str:
    return os.path.join(dest_folder or "", ".jav-downloader-jobs.json")


class JobStore:
    """Write/read resumable jobs with SQLite, atomic per transaction."""

    def __init__(self, dest_folder: str) -> None:
        self._path = store_path(dest_folder)
        self._legacy_json = legacy_json_path(dest_folder)
        self._lock = threading.Lock()
        self._last_signature: tuple | None = None
        self._init_db()
        self._import_legacy_json()

    @property
    def path(self) -> str:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        parent = os.path.dirname(self._path) or "."
        os.makedirs(parent, exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def _import_legacy_json(self) -> None:
        if not os.path.isfile(self._legacy_json):
            return
        try:
            jobs, params_by_id = self._load_json_file(self._legacy_json)
        except (OSError, ValueError):
            return
        if not jobs:
            return
        with self._lock:
            conn = self._connect()
            try:
                existing = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                if existing:
                    return
                for job in jobs:
                    params = params_by_id.get(job.id) or {}
                    self._upsert_locked(conn, job, params)
                conn.commit()
            finally:
                conn.close()

    def _load_json_file(self, path: str) -> tuple[list[Job], dict[str, dict]]:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return [], {}
        records = payload.get("jobs")
        if not isinstance(records, list):
            return [], {}
        jobs: list[Job] = []
        params_by_id: dict[str, dict] = {}
        for record in records:
            if not isinstance(record, dict) or not record.get("id"):
                continue
            job = Job(id=str(record["id"]), url=str(record.get("url") or ""))
            for field in _JOB_FIELDS:
                if field == "id":
                    continue
                if field in record and record[field] is not None:
                    value = record[field]
                    if field == "status":
                        value = JobStatus(str(value))
                    setattr(job, field, value)
            if job.status not in _RESUMABLE_STATUSES:
                job.status = JobStatus.PAUSED
            jobs.append(job)
            params = record.get("params")
            if isinstance(params, dict) and params.get("url"):
                params_by_id[job.id] = params
        return jobs, params_by_id

    def _signature(self, jobs: list[Job], params_by_id: dict[str, dict]) -> tuple:
        rows = []
        for job in jobs:
            if job.status not in _RESUMABLE_STATUSES:
                continue
            rows.append(
                (
                    job.id,
                    job.status.value
                if isinstance(job.status, JobStatus)
                else str(job.status),
                    job.updated_at,
                    json.dumps(params_by_id.get(job.id) or {}, sort_keys=True),
                )
            )
        return tuple(sorted(rows))

    def _upsert_locked(
        self, conn: sqlite3.Connection, job: Job, params: dict
    ) -> None:
        conn.execute(
            """
            INSERT INTO jobs (
                id, url, status, title, site, thumbnail, dest_folder, output_file,
                downloaded, total, progress_pct, progress_unit, progress_phase,
                progress_detail, error, log_json, created_at, started_at,
                completed_at, updated_at, params_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                url=excluded.url,
                status=excluded.status,
                title=excluded.title,
                site=excluded.site,
                thumbnail=excluded.thumbnail,
                dest_folder=excluded.dest_folder,
                output_file=excluded.output_file,
                downloaded=excluded.downloaded,
                total=excluded.total,
                progress_pct=excluded.progress_pct,
                progress_unit=excluded.progress_unit,
                progress_phase=excluded.progress_phase,
                progress_detail=excluded.progress_detail,
                error=excluded.error,
                log_json=excluded.log_json,
                created_at=excluded.created_at,
                started_at=excluded.started_at,
                completed_at=excluded.completed_at,
                updated_at=excluded.updated_at,
                params_json=excluded.params_json
            """,
            (
                job.id,
                job.url,
                job.status.value
                if isinstance(job.status, JobStatus)
                else str(job.status),
                job.title,
                job.site,
                job.thumbnail,
                job.dest_folder,
                job.output_file,
                int(job.downloaded),
                int(job.total),
                float(job.progress_pct),
                job.progress_unit,
                job.progress_phase,
                job.progress_detail,
                job.error,
                json.dumps(list(job.log), ensure_ascii=False),
                float(job.created_at),
                float(job.started_at),
                float(job.completed_at),
                float(job.updated_at),
                json.dumps(params, ensure_ascii=False),
            ),
        )

    def save(self, jobs: list[Job], params_by_id: dict[str, dict] | None = None) -> None:
        params_by_id = params_by_id or {}
        signature = self._signature(jobs, params_by_id)
        if signature == self._last_signature:
            return
        resumable_ids = {
            job.id for job in jobs if job.status in _RESUMABLE_STATUSES
        }
        with self._lock:
            try:
                conn = self._connect()
                try:
                    if resumable_ids:
                        placeholders = ",".join("?" for _ in resumable_ids)
                        conn.execute(
                            f"DELETE FROM jobs WHERE id NOT IN ({placeholders})",
                            tuple(resumable_ids),
                        )
                    else:
                        conn.execute("DELETE FROM jobs")
                    for job in jobs:
                        if job.status not in _RESUMABLE_STATUSES:
                            continue
                        params = params_by_id.get(job.id)
                        if not isinstance(params, dict) or not params.get("url"):
                            continue
                        self._upsert_locked(conn, job, params)
                    conn.commit()
                    self._last_signature = signature
                finally:
                    conn.close()
            except OSError:
                pass

    def load(self) -> tuple[list[Job], dict[str, dict]]:
        """Return (jobs, resume params by job id) from the store."""
        with self._lock:
            try:
                conn = self._connect()
            except OSError:
                return [], {}
            try:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY updated_at DESC"
                ).fetchall()
            finally:
                conn.close()
        jobs: list[Job] = []
        params_by_id: dict[str, dict] = {}
        for row in rows:
            job = Job(id=str(row["id"]), url=str(row["url"] or ""))
            job.status = JobStatus(str(row["status"]))
            job.title = row["title"] or ""
            job.site = row["site"] or ""
            job.thumbnail = row["thumbnail"] or ""
            job.dest_folder = row["dest_folder"] or ""
            job.output_file = row["output_file"] or ""
            job.downloaded = int(row["downloaded"] or 0)
            job.total = int(row["total"] or 0)
            job.progress_pct = float(row["progress_pct"] or 0)
            job.progress_unit = row["progress_unit"] or ""
            job.progress_phase = row["progress_phase"] or ""
            job.progress_detail = row["progress_detail"] or ""
            job.error = row["error"] or ""
            try:
                log = json.loads(row["log_json"] or "[]")
                job.log = log if isinstance(log, list) else []
            except ValueError:
                job.log = []
            job.created_at = float(row["created_at"] or 0)
            job.started_at = float(row["started_at"] or 0)
            job.completed_at = float(row["completed_at"] or 0)
            job.updated_at = float(row["updated_at"] or 0)
            if job.status not in _RESUMABLE_STATUSES:
                job.status = JobStatus.PAUSED
            jobs.append(job)
            try:
                params = json.loads(row["params_json"] or "{}")
            except ValueError:
                params = {}
            if isinstance(params, dict) and params.get("url"):
                params_by_id[job.id] = params
        return jobs, params_by_id

    def delete(self, job_id: str) -> None:
        with self._lock:
            try:
                conn = self._connect()
                try:
                    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
                    conn.commit()
                    self._last_signature = None
                finally:
                    conn.close()
            except OSError:
                pass
