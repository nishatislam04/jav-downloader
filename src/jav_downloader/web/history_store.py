"""Durable download history in app data (all job statuses, unlimited rows)."""

from __future__ import annotations

import json
import os
import shutil
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
CREATE TABLE IF NOT EXISTS download_log_lines (
    record_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    line TEXT NOT NULL,
    PRIMARY KEY (record_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_download_log_record
    ON download_log_lines(record_id, seq);
"""

_TERMINAL = frozenset({JobStatus.COMPLETED, JobStatus.FAILED})
_FLUSH_SEC = 2.0
_backup_done_for: set[str] = set()


def history_db_path(appdata: str | os.PathLike | None = None) -> str:
    root = product_data_dir(appdata, migrate=True)
    root.mkdir(parents=True, exist_ok=True)
    return str(root / "history.sqlite")


def _lines_to_append(db_lines: list[str], memory_lines: list[str]) -> list[str]:
    if not memory_lines:
        return []
    max_overlap = min(len(db_lines), len(memory_lines))
    for overlap in range(max_overlap, -1, -1):
        if overlap == 0:
            return list(memory_lines)
        if db_lines[-overlap:] == memory_lines[:overlap]:
            return list(memory_lines[overlap:])
    return list(memory_lines)


class HistoryStore:
    """SQLite history beside user app data, not the download folder."""

    def __init__(self, appdata: str | os.PathLike | None = None) -> None:
        self._path = history_db_path(appdata)
        self._lock = threading.Lock()
        self._last_flush: dict[str, float] = {}
        self._last_error: str = ""
        self._backup_once()
        self._init_db()

    @property
    def path(self) -> str:
        return self._path

    @property
    def last_error(self) -> str:
        return self._last_error

    def health_snapshot(self) -> dict:
        return {
            "history_db": self._path,
            "history_ok": not self._last_error,
            "history_last_error": self._last_error or None,
        }

    def _note_error(self, exc: BaseException) -> None:
        self._last_error = str(exc)

    def _clear_error(self) -> None:
        self._last_error = ""

    def _backup_once(self) -> None:
        if self._path in _backup_done_for:
            return
        _backup_done_for.add(self._path)
        if not os.path.isfile(self._path):
            return
        backup_path = f"{self._path}.bak"
        try:
            shutil.copy2(self._path, backup_path)
        except OSError as exc:
            self._note_error(exc)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
                self._migrate_log_json_to_lines(conn)
                conn.commit()
                self._clear_error()
            except (OSError, sqlite3.Error) as exc:
                self._note_error(exc)
            finally:
                conn.close()

    def _migrate_log_json_to_lines(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT id, log_json FROM download_records WHERE log_json != '[]'"
        ).fetchall()
        for row in rows:
            record_id = str(row["id"])
            count = conn.execute(
                "SELECT COUNT(*) FROM download_log_lines WHERE record_id = ?",
                (record_id,),
            ).fetchone()[0]
            if count:
                continue
            try:
                log = json.loads(row["log_json"] or "[]")
            except ValueError:
                log = []
            if not isinstance(log, list) or not log:
                continue
            for seq, line in enumerate(log):
                conn.execute(
                    """
                    INSERT INTO download_log_lines (record_id, seq, line)
                    VALUES (?, ?, ?)
                    """,
                    (record_id, seq, str(line)),
                )
            conn.execute(
                "UPDATE download_records SET log_json = '[]' WHERE id = ?",
                (record_id,),
            )

    def _downloaded_at(self, job: Job) -> float:
        if job.status == JobStatus.COMPLETED and job.completed_at > 0:
            return float(job.completed_at)
        if job.updated_at > 0:
            return float(job.updated_at)
        return float(job.created_at or time.time())

    def _fetch_log_lines(self, conn: sqlite3.Connection, record_id: str) -> list[str]:
        rows = conn.execute(
            """
            SELECT line FROM download_log_lines
            WHERE record_id = ?
            ORDER BY seq
            """,
            (record_id,),
        ).fetchall()
        return [str(row["line"]) for row in rows]

    def _append_log_lines(
        self, conn: sqlite3.Connection, record_id: str, new_lines: list[str]
    ) -> None:
        if not new_lines:
            return
        start = conn.execute(
            "SELECT COALESCE(MAX(seq), -1) FROM download_log_lines WHERE record_id = ?",
            (record_id,),
        ).fetchone()[0]
        seq = int(start) + 1
        for line in new_lines:
            conn.execute(
                """
                INSERT INTO download_log_lines (record_id, seq, line)
                VALUES (?, ?, ?)
                """,
                (record_id, seq, str(line)),
            )
            seq += 1

    def _sync_job_log(self, conn: sqlite3.Connection, record_id: str, job: Job) -> None:
        memory_lines = [str(line) for line in list(job.log)]
        db_lines = self._fetch_log_lines(conn, record_id)
        to_add = _lines_to_append(db_lines, memory_lines)
        self._append_log_lines(conn, record_id, to_add)

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
            "[]",
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
                    self._sync_job_log(conn, job.id, job)
                    conn.commit()
                    self._clear_error()
                finally:
                    conn.close()
            except (OSError, sqlite3.Error) as exc:
                self._note_error(exc)

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

    def count_records(self) -> int:
        with self._lock:
            try:
                conn = self._connect()
            except (OSError, sqlite3.Error) as exc:
                self._note_error(exc)
                return 0
            try:
                return int(
                    conn.execute("SELECT COUNT(*) FROM download_records").fetchone()[0]
                )
            finally:
                conn.close()

    def list_records(self, limit: int = 1000, offset: int = 0) -> list[dict]:
        limit = max(1, min(int(limit), 10000))
        offset = max(0, int(offset))
        with self._lock:
            try:
                conn = self._connect()
            except (OSError, sqlite3.Error) as exc:
                self._note_error(exc)
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

    def list_page(self, limit: int = 1000, offset: int = 0) -> dict:
        entries = self.list_records(limit=limit, offset=offset)
        total = self.count_records()
        return {
            "entries": entries,
            "total": total,
            "has_more": offset + len(entries) < total,
        }

    def get_record(self, record_id: str) -> dict | None:
        with self._lock:
            try:
                conn = self._connect()
            except (OSError, sqlite3.Error) as exc:
                self._note_error(exc)
                return None
            try:
                row = conn.execute(
                    "SELECT * FROM download_records WHERE id = ?",
                    (record_id,),
                ).fetchone()
                if row is None:
                    return None
                log = self._fetch_log_lines(conn, str(row["id"]))
                if not log:
                    try:
                        legacy = json.loads(row["log_json"] or "[]")
                        if isinstance(legacy, list):
                            log = [str(item) for item in legacy]
                    except ValueError:
                        log = []
            finally:
                conn.close()
        return self._row_to_full_dict(row, log)

    def _row_to_full_dict(self, row: sqlite3.Row, log: list[str]) -> dict:
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
            "log": log,
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
                    conn.execute(
                        "DELETE FROM download_log_lines WHERE record_id = ?",
                        (record_id,),
                    )
                    cur = conn.execute(
                        "DELETE FROM download_records WHERE id = ?",
                        (record_id,),
                    )
                    conn.commit()
                    self._clear_error()
                    return cur.rowcount > 0
                finally:
                    conn.close()
            except (OSError, sqlite3.Error) as exc:
                self._note_error(exc)
                return False

    def clear_all(self) -> None:
        with self._lock:
            try:
                conn = self._connect()
                try:
                    conn.execute("DELETE FROM download_log_lines")
                    conn.execute("DELETE FROM download_records")
                    conn.commit()
                    self._last_flush.clear()
                    self._clear_error()
                finally:
                    conn.close()
            except (OSError, sqlite3.Error) as exc:
                self._note_error(exc)

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
