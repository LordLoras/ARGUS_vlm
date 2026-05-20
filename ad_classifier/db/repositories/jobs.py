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

    def list(
        self,
        *,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        if state:
            clauses.append("j.state = ?")
            params.append(state)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT
              j.*,
              a.status AS ad_status,
              a.source_path AS source_path,
              a.brand_name AS brand_name,
              a.primary_category AS primary_category,
              a.ingested_at AS ingested_at
            FROM jobs j
            LEFT JOIN ads a ON a.id = j.ad_id
            {where}
            ORDER BY
              CASE j.state
                WHEN 'running' THEN 0
                WHEN 'queued' THEN 1
                WHEN 'failed' THEN 2
                WHEN 'cancelled' THEN 3
                WHEN 'completed' THEN 4
                ELSE 5
              END,
              j.rowid DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
        return [row_to_dict(row) or {} for row in rows]

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

    def delete(self, job_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cur.rowcount > 0

    def requeue_running(self, *, message: str = "requeued after restart") -> int:
        cur = self.conn.execute(
            """
            UPDATE jobs
            SET state = 'queued',
                progress = 0.0,
                message = ?,
                error = NULL,
                started_at = NULL,
                finished_at = NULL
            WHERE state = 'running'
            """,
            (message,),
        )
        return cur.rowcount
