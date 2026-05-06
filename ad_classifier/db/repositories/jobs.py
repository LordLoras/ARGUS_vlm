from __future__ import annotations

import sqlite3
from datetime import datetime

from ad_classifier.db.repositories.base import db_value, row_to_dict
from ad_classifier.models.jobs import JobRecord, JobState


class JobRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, job: JobRecord) -> None:
        data = job.model_dump()
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = [db_value(value) for value in data.values()]
        self.conn.execute(
            f"INSERT INTO jobs ({columns}) VALUES ({placeholders})",
            values,
        )

    def get(self, job_id: str) -> JobRecord | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        data = row_to_dict(row)
        return JobRecord.model_validate(data) if data is not None else None

    def next_queued(self) -> JobRecord | None:
        row = self.conn.execute("""
            SELECT *
            FROM jobs
            WHERE state = 'queued'
            ORDER BY rowid
            LIMIT 1
            """).fetchone()
        data = row_to_dict(row)
        return JobRecord.model_validate(data) if data is not None else None

    def update_state(
        self,
        job_id: str,
        *,
        state: JobState,
        progress: float | None = None,
        message: str | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE jobs
            SET state = ?,
                progress = ?,
                message = ?,
                error = ?,
                started_at = COALESCE(?, started_at),
                finished_at = COALESCE(?, finished_at)
            WHERE id = ?
            """,
            (
                state,
                progress,
                message,
                error,
                db_value(started_at),
                db_value(finished_at),
                job_id,
            ),
        )

    def cancel(self, job_id: str, *, message: str = "cancelled") -> bool:
        cur = self.conn.execute(
            """
            UPDATE jobs
            SET state = 'cancelled',
                message = ?,
                finished_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND state IN ('queued', 'running')
            """,
            (message, job_id),
        )
        return cur.rowcount > 0
