"""SQLite job state for the image API.

One row per submitted job. Stable schema: jobs are append-only except
for the lifecycle columns (`status`, `output_urls`, `cost_usd`, `error`,
`updated_at`). The DB file lives outside the package so it survives
upgrades.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from .schemas import JobStatus


SCHEMA = """
CREATE TABLE IF NOT EXISTS image_jobs (
    job_id           TEXT PRIMARY KEY,
    project_slug     TEXT NOT NULL,
    spec_yaml        TEXT NOT NULL,
    status           TEXT NOT NULL,
    output_urls_json TEXT NOT NULL DEFAULT '[]',
    cost_usd         REAL,
    error            TEXT,
    content_piece_id INTEGER,
    model_used       TEXT,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_image_jobs_status ON image_jobs(status);
CREATE INDEX IF NOT EXISTS idx_image_jobs_project ON image_jobs(project_slug);
"""


@dataclass
class JobRecord:
    job_id: str
    project_slug: str
    spec_yaml: str
    status: JobStatus
    output_urls: list[str]
    cost_usd: Optional[float]
    error: Optional[str]
    content_piece_id: Optional[int]
    model_used: Optional[str]
    created_at: float
    updated_at: float


class JobsDB:
    """Thin wrapper around SQLite. Thread-safe via per-call connections."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            yield conn
        finally:
            conn.close()

    # ---- writes ---------------------------------------------------------

    def insert(
        self,
        *,
        job_id: str,
        project_slug: str,
        spec_yaml: str,
        content_piece_id: Optional[int] = None,
        now: Optional[float] = None,
    ) -> JobRecord:
        ts = now if now is not None else time.time()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO image_jobs
                   (job_id, project_slug, spec_yaml, status, output_urls_json,
                    content_piece_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, project_slug, spec_yaml, JobStatus.queued.value, "[]",
                 content_piece_id, ts, ts),
            )
        rec = self.get(job_id)
        assert rec is not None
        return rec

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        *,
        output_urls: Optional[list[str]] = None,
        cost_usd: Optional[float] = None,
        error: Optional[str] = None,
        model_used: Optional[str] = None,
        now: Optional[float] = None,
    ) -> JobRecord:
        ts = now if now is not None else time.time()
        sets: list[str] = ["status = ?", "updated_at = ?"]
        args: list[object] = [status.value, ts]
        if output_urls is not None:
            sets.append("output_urls_json = ?")
            args.append(json.dumps(list(output_urls)))
        if cost_usd is not None:
            sets.append("cost_usd = ?")
            args.append(float(cost_usd))
        if error is not None:
            sets.append("error = ?")
            args.append(error)
        if model_used is not None:
            sets.append("model_used = ?")
            args.append(model_used)
        args.append(job_id)
        with self._connect() as conn:
            conn.execute(
                f"UPDATE image_jobs SET {', '.join(sets)} WHERE job_id = ?",
                args,
            )
        rec = self.get(job_id)
        if rec is None:
            raise KeyError(job_id)
        return rec

    # ---- reads ----------------------------------------------------------

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM image_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    def list_pending(self, *, limit: int = 32) -> list[JobRecord]:
        """Return jobs in non-terminal states, oldest first."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM image_jobs
                   WHERE status NOT IN (?, ?)
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (JobStatus.completed.value, JobStatus.failed.value, limit),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            project_slug=row["project_slug"],
            spec_yaml=row["spec_yaml"],
            status=JobStatus(row["status"]),
            output_urls=json.loads(row["output_urls_json"] or "[]"),
            cost_usd=row["cost_usd"],
            error=row["error"],
            content_piece_id=row["content_piece_id"],
            model_used=row["model_used"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
