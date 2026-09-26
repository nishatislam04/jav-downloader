"""Durable download history in app data (all job statuses, unlimited rows)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time

from jav_downloader.core.paths import product_data_dir
from jav_downloader.web.jobs import Job, JobStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS download_records (
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
    speed REAL NOT NULL DEFAULT 0,
    progress_pct REAL NOT NULL DEFAULT 0,
    progress_unit TEXT NOT NULL DEFAULT '',
    progress_phase TEXT NOT NULL DEFAULT '',
    progress_detail TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    log_json TEXT NOT NULL DEFAULT '[]',
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL DEFAULT 0,
    started_at REAL NOT NULL DEFAULT 0,
    completed_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0,
    elapsed_sec REAL NOT NULL DEFAULT 0,
    download_phase_sec REAL NOT NULL DEFAULT 0,
    encode_phase_sec REAL NOT NULL DEFAULT 0,
    downloaded_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_download_records_updated
    ON download_records(updated_at DESC);
"""

_TERMINAL = frozenset({JobStatus.COMPLETED, JobStatus.FAILED})
_FLUSH_SEC = 2.0


def history_db_path(appdata: str | os.PathLike | None = None) -> str:
    root = product_data_dir(appdata, migrate=True)
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "history.sqlite")


class HistoryStore:
    """SQLite history beside user app data, not the download folder."""

    def __init__(self, appdata: str | os.PathLike | None = None) -> None:
        self._path = history_db_path(appdata)
        self._lock = threading.Lock()
        self._last_flush: dict[str, float] = {}
        self._init_db()

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
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def _downloaded_at(self, job: Job) -> float:
        if job.status == JobStatus.COMPLETED and job.completed_at > 0:
            return float(job.completed_at)
        if job.updated_at > 0:
            return float(job.updated_at)
        return float(job.created_at or time.time())

    def upsert_job(self, job: Job, meta: dict | None = None) -> None:
        status = (
            job.status.value
            if isinstance(job.status, JobStatus)
            else str(job.status)
        )
        meta_payload = dict(meta or {})
        row = (
            job.id,
            job.url or "",
            status,
            job.title or "",
            job.site or "",
            job.thumbnail or "",
            job.dest_folder or "",
            job.output_file or "",
            int(job.downloaded),
            int(job.total),
            float(job.speed),
            float(job.progress_pct),
            job.progress_unit or "",
            job.progress_phase or "",
            job.progress_detail or "",
            job.error or "",
            json.dumps(list(job.log), ensure_ascii=False),
            json.dumps(meta_payload, ensure_ascii=False),
            float(job.created_at or 0),
            float(job.started_at or 0),
            float(job.completed_at or 0),
            float(job.updated_at or 0),
            float(job.elapsed_sec),
            float(job.download_phase_sec),
            float(job.encode_phase_sec),
            self._downloaded_at(job),
        )
        with self._lock:
            try:
                conn = self._connect()
                try:
                    conn.execute(
                        """
                        INSERT INTO download_records (
                            id, url, status, title, site, thumbnail, dest_folder,
                            output_file, downloaded, total, speed, progress_pct,
                            progress_unit, progress_phase, progress_detail, error,
                            log_json, meta_json, created_at, started_at, completed_at,
                            updated_at, elapsed_sec, download_phase_sec,
                            encode_phase_sec, downloaded_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            speed=excluded.speed,
                            progress_pct=excluded.progress_pct,
                            progress_unit=excluded.progress_unit,
                            progress_phase=excluded.progress_phase,
                            progress_detail=excluded.progress_detail,
                            error=excluded.error,
                            log_json=excluded.log_json,
                            meta_json=excluded.meta_json,
                            created_at=excluded.created_at,
                            started_at=excluded.started_at,
                            completed_at=excluded.completed_at,
                            updated_at=excluded.updated_at,
                            elapsed_sec=excluded.elapsed_sec,
                            download_phase_sec=excluded.download_phase_sec,
                            encode_phase_sec=excluded.encode_phase_sec,
                            downloaded_at=excluded.downloaded_at
                        """,
                        row,
                    )
                    conn.commit()
                finally:
                    conn.close()
            except OSError:
                pass

    def upsert_jobs_throttled(
        self, jobs: list[Job], params_by_id: dict[str, dict] | None = None
    ) -> None:
        params_by_id = params_by_id or {}
        now = time.time()
        for job in jobs:
            terminal = job.status in _TERMINAL
            if not terminal:
                last = self._last_flush.get(job.id, 0.0)
                if now - last < _FLUSH_SEC:
                    continue
            self._last_flush[job.id] = now
            meta = params_by_id.get(job.id)
            self.upsert_job(job, meta if isinstance(meta, dict) else None)

    def list_records(self, limit: int = 1000, offset: int = 0) -> list[dict]:
        limit = max(1, min(int(limit), 10000))
        offset = max(0, int(offset))
        with self._lock:
            try:
                conn = self._connect()
            except OSError:
                return []
            try:
                rows = conn.execute(
                    """
                    SELECT id, url, title, thumbnail, status, downloaded_at, updated_at
                    FROM download_records
                    ORDER BY updated_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
            finally:
                conn.close()
        return [
            {
                "id": str(row["id"]),
                "url": row["url"] or "",
                "title": row["title"] or "",
                "thumbnail": row["thumbnail"] or "",
                "status": row["status"] or "",
                "downloadedAt": float(row["downloaded_at"] or 0),
                "updatedAt": float(row["updated_at"] or 0),
            }
            for row in rows
        ]

    def get_record(self, record_id: str) -> dict | None:
        with self._lock:
            try:
                conn = self._connect()
            except OSError:
                return None
            try:
                row = conn.execute(
                    "SELECT * FROM download_records WHERE id = ?",
                    (record_id,),
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        return self._row_to_full_dict(row)

    def _row_to_full_dict(self, row: sqlite3.Row) -> dict:
        try:
            log = json.loads(row["log_json"] or "[]")
        except ValueError:
            log = []
        try:
            meta = json.loads(row["meta_json"] or "{}")
        except ValueError:
            meta = {}
        return {
            "id": str(row["id"]),
            "url": row["url"] or "",
            "status": row["status"] or "",
            "title": row["title"] or "",
            "site": row["site"] or "",
            "thumbnail": row["thumbnail"] or "",
            "dest_folder": row["dest_folder"] or "",
            "output_file": row["output_file"] or "",
            "downloaded": int(row["downloaded"] or 0),
            "total": int(row["total"] or 0),
            "speed": float(row["speed"] or 0),
            "progress_pct": float(row["progress_pct"] or 0),
            "progress_unit": row["progress_unit"] or "",
            "progress_phase": row["progress_phase"] or "",
            "progress_detail": row["progress_detail"] or "",
            "error": row["error"] or "",
            "log": log if isinstance(log, list) else [],
            "meta": meta if isinstance(meta, dict) else {},
            "created_at": float(row["created_at"] or 0),
            "started_at": float(row["started_at"] or 0),
            "completed_at": float(row["completed_at"] or 0),
            "updated_at": float(row["updated_at"] or 0),
            "elapsed_sec": float(row["elapsed_sec"] or 0),
            "download_phase_sec": float(row["download_phase_sec"] or 0),
            "encode_phase_sec": float(row["encode_phase_sec"] or 0),
            "downloadedAt": float(row["downloaded_at"] or 0),
        }

    def delete(self, record_id: str) -> bool:
        with self._lock:
            try:
                conn = self._connect()
                try:
                    cur = conn.execute(
                        "DELETE FROM download_records WHERE id = ?",
                        (record_id,),
                    )
                    conn.commit()
                    return cur.rowcount > 0
                finally:
                    conn.close()
            except OSError:
                return False

    def clear_all(self) -> None:
        with self._lock:
            try:
                conn = self._connect()
                try:
                    conn.execute("DELETE FROM download_records")
                    conn.commit()
                    self._last_flush.clear()
                finally:
                    conn.close()
            except OSError:
                pass

    def import_menu_entries(self, entries: list[dict]) -> int:
        """Import legacy browser history rows (id, url, title, thumbnail, downloadedAt)."""
        imported = 0
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            record_id = str(raw.get("id") or "").strip()
            url = str(raw.get("url") or "").strip()
            if not record_id or not url:
                continue
            job = Job(id=record_id, url=url, status=JobStatus.COMPLETED)
            job.title = str(raw.get("title") or "")
            job.thumbnail = str(raw.get("thumbnail") or "")
            ts = raw.get("downloadedAt")
            try:
                downloaded_at = float(ts)
            except (TypeError, ValueError):
                downloaded_at = time.time()
            if downloaded_at > 1e12:
                downloaded_at /= 1000.0
            job.completed_at = downloaded_at
            job.updated_at = downloaded_at
            job.created_at = downloaded_at
            self.upsert_job(job)
            imported += 1
        return imported
