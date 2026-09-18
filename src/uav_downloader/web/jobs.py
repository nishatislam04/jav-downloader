"""In-memory download job tracking for the web UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import uuid


class JobStatus(str, Enum):
    PENDING = 'pending'
    DOWNLOADING = 'downloading'
    PAUSED = 'paused'
    COMPLETED = 'completed'
    FAILED = 'failed'


@dataclass
class Job:
    id: str
    url: str
    status: JobStatus = JobStatus.PENDING
    title: str = ''
    site: str = ''
    thumbnail: str = ''
    dest_folder: str = ''
    output_file: str = ''
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    progress_pct: float = 0.0
    progress_unit: str = ''  # 'bytes', 'segments', or '' when unknown
    error: str = ''
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'url': self.url,
            'status': self.status.value,
            'title': self.title,
            'site': self.site,
            'thumbnail': self.thumbnail,
            'dest_folder': self.dest_folder,
            'output_file': self.output_file,
            'downloaded': self.downloaded,
            'total': self.total,
            'speed': self.speed,
            'progress_pct': self.progress_pct,
            'progress_unit': self.progress_unit,
            'error': self.error,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, url: str) -> Job:
        job = Job(id=uuid.uuid4().hex, url=url)
        with self._lock:
            self._jobs[job.id] = job
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
            return job

    def set_progress(
            self,
            job_id: str,
            downloaded: int,
            total: int,
            speed: float,
            *,
            progress_unit: str = '') -> None:
        pct = (downloaded / total * 100.0) if total > 0 else 0.0
        self.update(
            job_id,
            downloaded=downloaded,
            total=total,
            speed=speed,
            progress_pct=round(pct, 2),
            progress_unit=progress_unit,
            status=JobStatus.DOWNLOADING,
        )
