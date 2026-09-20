"""Persist paused jobs so Resume works across server restarts.

The job store is a small JSON file next to the download folder. Only jobs that
can still be resumed (paused, or waiting to start) are written; completed and
failed jobs stay in memory only. Restored jobs keep their id, log and progress
snapshot so the UI looks unchanged after a restart.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading

from jav_downloader.web.jobs import Job, JobStatus

# Job fields persisted and restored. `log` is capped already; progress fields
# give the UI a sane snapshot until the resumed download updates them.
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


def store_path(dest_folder: str) -> str:
    """JSON file lives beside the downloads so it survives restarts."""
    return os.path.join(dest_folder or "", ".jav-downloader-jobs.json")


class JobStore:
    """Write/read the resumable-job file, with atomic replaces and a lock."""

    def __init__(self, dest_folder: str) -> None:
        self._path = store_path(dest_folder)
        self._lock = threading.Lock()
        self._last_payload: str | None = None

    @property
    def path(self) -> str:
        return self._path

    def save(self, jobs: list[Job], params_by_id: dict[str, dict] | None = None) -> None:
        params_by_id = params_by_id or {}
        records = []
        for job in jobs:
            if job.status not in _RESUMABLE_STATUSES:
                continue
            record = {field: getattr(job, field) for field in _JOB_FIELDS}
            params = params_by_id.get(job.id)
            if isinstance(params, dict) and params.get("url"):
                record["params"] = params
            records.append(record)
        payload = {"version": 1, "jobs": records}
        body = json.dumps(payload, ensure_ascii=False)
        if body == self._last_payload:
            return
        with self._lock:
            try:
                parent = os.path.dirname(self._path) or "."
                fd, tmp = tempfile.mkstemp(
                    prefix=".jav-jobs-", suffix=".tmp", dir=parent
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write(body)
                    os.replace(tmp, self._path)
                except BaseException:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    raise
                self._last_payload = body
            except OSError:
                # Persistence is best-effort; in-memory state stays usable.
                pass

    def load(self) -> tuple[list[Job], dict[str, dict]]:
        """Return (jobs, resume params by job id) from the store."""
        try:
            with open(self._path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            return [], {}
        if not isinstance(payload, dict):
            return [], {}
        records = payload.get("jobs")
        if not isinstance(records, list):
            return [], {}
        jobs = []
        params_by_id: dict[str, dict] = {}
        for record in records:
            if not isinstance(record, dict) or not record.get("id"):
                continue
            job = Job(id=str(record["id"]), url=str(record.get("url") or ""))
            for field in _JOB_FIELDS:
                if field == "id":
                    continue
                if field in record and record[field] is not None:
                    setattr(job, field, record[field])
            # Only resumable states are meaningful across restarts.
            if job.status not in _RESUMABLE_STATUSES:
                job.status = JobStatus.PAUSED
            jobs.append(job)
            params = record.get("params")
            if isinstance(params, dict) and params.get("url"):
                params_by_id[job.id] = params
        return jobs, params_by_id
