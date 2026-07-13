"""Durable queue claims, recovery, and worker/scheduler service heartbeats."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from ad_classifier.entity_graph.rows import loads_dict, to_json
from ad_classifier.intelligence_crawler.timeutils import iso, parse_iso


class RuntimeRepositoryMixin:
    def queue_run(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        request: dict,
        *,
        idempotency_key: str | None = None,
        attempt_count: int = 0,
    ) -> str:
        if idempotency_key:
            existing = conn.execute(
                "SELECT id FROM intel_crawl_runs WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                return str(existing["id"])
        try:
            conn.execute(
                """
                INSERT INTO intel_crawl_runs
                  (id, status, summary_json, request_json, idempotency_key, attempt_count)
                VALUES (?, 'queued', ?, ?, ?, ?)
                """,
                (
                    run_id,
                    to_json({"request": request}),
                    to_json(request),
                    idempotency_key,
                    attempt_count,
                ),
            )
            return run_id
        except sqlite3.IntegrityError:
            if not idempotency_key:
                raise
            existing = conn.execute(
                "SELECT id FROM intel_crawl_runs WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is None:
                raise
            return str(existing["id"])

    def start_run(self, conn: sqlite3.Connection, run_id: str) -> None:
        conn.execute(
            "UPDATE intel_crawl_runs SET status='running', started_at=datetime('now'), "
            "attempt_count=attempt_count + 1 "
            "WHERE id=? AND status='queued'",
            (run_id,),
        )

    def claim_next_run(
        self,
        conn: sqlite3.Connection,
        *,
        owner: str,
        now: datetime,
        lease_seconds: int,
    ) -> dict | None:
        """Atomically claim the oldest queued run for one worker process."""

        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM intel_crawl_runs WHERE status='queued' "
            "ORDER BY started_at, id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        run_id = str(row["id"])
        lease_until = now.astimezone(UTC) + timedelta(seconds=lease_seconds)
        claimed = conn.execute(
            """
            UPDATE intel_crawl_runs SET status='running', started_at=?, finished_at=NULL,
              lease_owner=?, lease_until=?, heartbeat_at=?, attempt_count=attempt_count + 1
            WHERE id=? AND status='queued'
            """,
            (iso(now), owner, iso(lease_until), iso(now), run_id),
        )
        if claimed.rowcount != 1:  # pragma: no cover - BEGIN IMMEDIATE serializes claimers
            return None
        result = self.get_run(conn, run_id)
        assert result is not None
        return result

    def renew_run_lease(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        *,
        owner: str,
        now: datetime,
        lease_seconds: int,
    ) -> bool:
        lease_until = now.astimezone(UTC) + timedelta(seconds=lease_seconds)
        updated = conn.execute(
            "UPDATE intel_crawl_runs SET heartbeat_at=?, lease_until=? "
            "WHERE id=? AND status='running' AND lease_owner=?",
            (iso(now), iso(lease_until), run_id, owner),
        )
        return updated.rowcount == 1

    def recover_abandoned_runs(
        self,
        conn: sqlite3.Connection,
        *,
        now: datetime,
        max_attempts: int,
        new_run_id: Callable[[], str],
    ) -> dict[str, list[str]]:
        """Fail expired worker leases and create fresh retry runs with the same request."""

        rows = conn.execute(
            """
            SELECT r.* FROM intel_crawl_runs r
            WHERE r.status='running' AND r.lease_owner IS NOT NULL
              AND r.lease_until IS NOT NULL AND r.lease_until <= ?
              AND NOT EXISTS (
                SELECT 1 FROM intel_source_state st
                WHERE st.lease_until IS NOT NULL AND st.lease_until > ?
                  AND instr(st.lease_owner, ':' || r.id || ':') > 0
              )
            ORDER BY lease_until
            """,
            (iso(now), iso(now)),
        ).fetchall()
        recovered: list[str] = []
        exhausted: list[str] = []
        for row in rows:
            run_id = str(row["id"])
            attempt_count = int(row["attempt_count"] or 0)
            request = loads_dict(row["request_json"]) or {}
            if attempt_count >= max_attempts:
                conn.execute(
                    """
                    UPDATE intel_crawl_runs SET status='failed', finished_at=?,
                      error=?, lease_owner=NULL, lease_until=NULL
                    WHERE id=? AND status='running'
                    """,
                    (
                        iso(now),
                        "Worker lease expired and the automatic retry limit was reached.",
                        run_id,
                    ),
                )
                exhausted.append(run_id)
                continue
            retry_id = new_run_id()
            retry_request = {**request, "recovered_from": run_id}
            self.queue_run(conn, retry_id, retry_request, attempt_count=attempt_count)
            conn.execute(
                """
                UPDATE intel_crawl_runs SET status='failed', finished_at=?, error=?,
                  summary_json=?, lease_owner=NULL, lease_until=NULL
                WHERE id=? AND status='running'
                """,
                (
                    iso(now),
                    "Worker lease expired; a replacement run was queued.",
                    to_json({"retry_run_id": retry_id, "request": request}),
                    run_id,
                ),
            )
            recovered.append(retry_id)
        return {"recovered": recovered, "exhausted": exhausted}

    def has_active_request_origin(self, conn: sqlite3.Connection, origin: str) -> bool:
        rows = conn.execute(
            "SELECT request_json FROM intel_crawl_runs WHERE status IN ('queued','running')"
        ).fetchall()
        return any((loads_dict(row["request_json"]) or {}).get("origin") == origin for row in rows)

    def queue_stats(self, conn: sqlite3.Connection, *, now: datetime) -> dict:
        counts = {
            str(row["status"]): int(row["n"])
            for row in conn.execute(
                "SELECT status, COUNT(*) AS n FROM intel_crawl_runs GROUP BY status"
            ).fetchall()
        }
        oldest = conn.execute(
            "SELECT MIN(started_at) AS value FROM intel_crawl_runs WHERE status='queued'"
        ).fetchone()
        abandoned = conn.execute(
            "SELECT COUNT(*) AS n FROM intel_crawl_runs WHERE status='running' "
            "AND lease_owner IS NOT NULL AND lease_until <= ?",
            (iso(now),),
        ).fetchone()
        return {
            "queued": counts.get("queued", 0),
            "running": counts.get("running", 0),
            "completed": counts.get("completed", 0),
            "degraded": counts.get("degraded", 0),
            "failed": counts.get("failed", 0),
            "oldest_queued_at": parse_iso(oldest["value"]) if oldest else None,
            "abandoned_running": int(abandoned["n"] or 0) if abandoned else 0,
        }

    def upsert_service_heartbeat(
        self,
        conn: sqlite3.Connection,
        *,
        service_name: str,
        instance_id: str,
        activity: str,
        now: datetime,
        metadata: dict | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO intel_service_heartbeats
              (service_name, instance_id, activity, started_at, heartbeat_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(service_name) DO UPDATE SET
              instance_id=excluded.instance_id,
              activity=excluded.activity,
              started_at=CASE
                WHEN intel_service_heartbeats.instance_id = excluded.instance_id
                THEN intel_service_heartbeats.started_at ELSE excluded.started_at END,
              heartbeat_at=excluded.heartbeat_at,
              metadata_json=excluded.metadata_json
            """,
            (service_name, instance_id, activity, iso(now), iso(now), to_json(metadata or {})),
        )

    def list_service_heartbeats(self, conn: sqlite3.Connection) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM intel_service_heartbeats ORDER BY service_name"
        ).fetchall()
        return [
            {
                "service_name": str(row["service_name"]),
                "instance_id": str(row["instance_id"]),
                "activity": str(row["activity"]),
                "started_at": parse_iso(row["started_at"]),
                "heartbeat_at": parse_iso(row["heartbeat_at"]),
                "metadata": loads_dict(row["metadata_json"]) or {},
            }
            for row in rows
        ]
