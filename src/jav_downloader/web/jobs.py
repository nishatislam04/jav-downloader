"""In-memory download job tracking for the web UI."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# Progress ticks must not overwrite these statuses.
_PROGRESS_LOCKED_STATUSES = frozenset(
    {
        JobStatus.PAUSED,
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.PENDING,
    }
)


@dataclass
class Job:
    id: str
    url: str
    status: JobStatus = JobStatus.PENDING
    title: str = ""
    site: str = ""
    thumbnail: str = ""
    dest_folder: str = ""
    output_file: str = ""
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    progress_pct: float = 0.0
    progress_unit: str = ""  # 'bytes', 'segments', or '' when unknown
    progress_phase: str = ""
    progress_detail: str = ""
    error: str = ""
    log: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    download_phase_sec: float = 0.0
    encode_phase_sec: float = 0.0
    updated_at: float = field(default_factory=time.time)

    @property
    def elapsed_sec(self) -> float:
        """Total download-to-encode wall time, 0 when not measurable."""
        if self.completed_at <= 0:
            return 0.0
        start = self.started_at if self.started_at > 0 else self.created_at
        return max(0.0, self.completed_at - start)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "status": self.status.value,
            "title": self.title,
            "site": self.site,
            "thumbnail": self.thumbnail,
            "dest_folder": self.dest_folder,
            "output_file": self.output_file,
            "downloaded": self.downloaded,
            "total": self.total,
            "speed": self.speed,
            "progress_pct": self.progress_pct,
            "progress_unit": self.progress_unit,
            "progress_phase": self.progress_phase,
            "progress_detail": self.progress_detail,
            "error": self.error,
            "log": list(self.log),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_sec": self.elapsed_sec,
            "download_phase_sec": self.download_phase_sec,
            "encode_phase_sec": self.encode_phase_sec,
            "updated_at": self.updated_at,
        }


class JobManager:
    def __init__(self, on_change=None) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        # Optional persistence hook: called with the full job list after each
        # mutation. Used to keep resumable jobs on disk across restarts.
        self._on_change = on_change

    def set_persistence(self, on_change) -> None:
        """Attach the persistence hook after construction."""
        self._on_change = on_change

    def _notify(self) -> None:
        if self._on_change is None:
            return
        try:
            self._on_change(list(self._jobs.values()))
        except Exception:
            pass

    def create(self, url: str) -> Job:
        job = Job(id=uuid.uuid4().hex, url=url)
        with self._lock:
            self._jobs[job.id] = job
        self._notify()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        with self._lock:
            return sorted(
                self._jobs.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )

    def update(self, job_id: str, **fields) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = time.time()
            snapshot = list(self._jobs.values())
        self._notify_with(snapshot)
        return job

    def restore_jobs(self, jobs: list[Job]) -> int:
        """Insert persisted jobs at startup; skips existing ids."""
        restored = 0
        with self._lock:
            for job in jobs:
                if job.id in self._jobs:
                    continue
                self._jobs[job.id] = job
                restored += 1
        if restored:
            self.notify_change()
        return restored

    def notify_change(self) -> None:
        """Re-emit the persistence hook after out-of-band mutations."""
        with self._lock:
            snapshot = list(self._jobs.values())
        self._notify_with(snapshot)

    # Persistence hook may itself call back into the manager (it must not
    # while the lock is held), so notifications run outside the lock.
    def _notify_with(self, jobs: list[Job]) -> None:
        if self._on_change is None:
            return
        try:
            self._on_change(jobs)
        except Exception:
            pass

    def append_log(self, job_id: str, message: str) -> None:
        text = str(message or "").strip()
        if not text:
            return
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.log.append(text)
            if len(job.log) > 250:
                job.log = job.log[-250:]
            job.updated_at = time.time()
            snapshot = list(self._jobs.values())
        self._notify_with(snapshot)

    def set_progress(
        self,
        job_id: str,
        downloaded: int,
        total: int,
        speed: float,
        *,
        progress_unit: str = "",
        progress_phase: str | None = None,
        progress_detail: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            pct = (downloaded / total * 100.0) if total > 0 else 0.0
            job.downloaded = downloaded
            job.total = total
            job.progress_pct = round(pct, 2)
            job.progress_unit = progress_unit
            if progress_phase is not None:
                job.progress_phase = progress_phase
            if progress_detail is not None:
                job.progress_detail = progress_detail
            # Never let stale worker progress clobber a paused job back to downloading.
            if job.status not in _PROGRESS_LOCKED_STATUSES:
                job.status = JobStatus.DOWNLOADING
                job.speed = speed
            elif job.status == JobStatus.PAUSED:
                job.speed = 0.0
            job.updated_at = time.time()
            snapshot = list(self._jobs.values())
        self._notify_with(snapshot)

    def set_phase(self, job_id: str, phase: str, detail: str = "") -> None:
        self.update(
            job_id,
            progress_phase=str(phase or ""),
            progress_detail=str(detail or ""),
        )
