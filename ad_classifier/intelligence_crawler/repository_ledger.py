"""Append-only observations and crawl/source-run ledger persistence."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ad_classifier.entity_graph.rows import loads_dict, to_json
from ad_classifier.intelligence_crawler.models import (
    IntelMediaAsset,
    IntelResourceObservation,
    PollDiagnostic,
    RunStatus,
)
from ad_classifier.intelligence_crawler.repository_rows import (
    crawl_run_dict,
    diagnostics_json,
    source_run_dict,
)
from ad_classifier.intelligence_crawler.timeutils import iso, parse_iso


class LedgerRepositoryMixin:
    def queue_run(self, conn: sqlite3.Connection, run_id: str, request: dict) -> None:
        conn.execute(
            "INSERT INTO intel_crawl_runs (id, status, summary_json) VALUES (?, 'queued', ?)",
            (run_id, to_json({"request": request})),
        )

    def start_run(self, conn: sqlite3.Connection, run_id: str) -> None:
        conn.execute(
            "UPDATE intel_crawl_runs SET status='running', started_at=datetime('now') "
            "WHERE id=? AND status='queued'",
            (run_id,),
        )

    def insert_observation(
        self, conn: sqlite3.Connection, observation: IntelResourceObservation
    ) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO intel_resource_observations
              (id, resource_id, source_id, run_id, observed_at, payload_hash,
               resource_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.id,
                observation.resource_id,
                observation.source_id,
                observation.run_id,
                iso(observation.observed_at),
                observation.payload_hash,
                to_json(observation.resource),
                to_json(observation.metadata),
            ),
        )

    def upsert_media_asset(self, conn: sqlite3.Connection, asset: IntelMediaAsset) -> None:
        conn.execute(
            """
            INSERT INTO intel_media_assets
              (id, resource_id, asset_type, url, thumbnail_url, duration_ms,
               content_hash, phash, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              url=excluded.url, thumbnail_url=excluded.thumbnail_url,
              duration_ms=excluded.duration_ms, content_hash=excluded.content_hash,
              phash=excluded.phash, metadata_json=excluded.metadata_json
            """,
            (
                asset.id,
                asset.resource_id,
                asset.asset_type,
                asset.url,
                asset.thumbnail_url,
                asset.duration_ms,
                asset.content_hash,
                asset.phash,
                to_json(asset.metadata),
            ),
        )

    def list_resource_observations(
        self, conn: sqlite3.Connection, resource_id: str, *, limit: int = 50
    ) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM intel_resource_observations WHERE resource_id = ? "
            "ORDER BY observed_at DESC LIMIT ?",
            (resource_id, limit),
        ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "resource_id": str(row["resource_id"]),
                "source_id": str(row["source_id"]),
                "run_id": str(row["run_id"]),
                "observed_at": parse_iso(row["observed_at"]),
                "payload_hash": str(row["payload_hash"]),
                "resource": loads_dict(row["resource_json"]) or {},
                "metadata": loads_dict(row["metadata_json"]) or {},
            }
            for row in rows
        ]

    def create_run(self, conn: sqlite3.Connection, run_id: str) -> None:
        conn.execute("INSERT INTO intel_crawl_runs (id, status) VALUES (?, 'running')", (run_id,))

    def start_source_run(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        source_id: str,
        *,
        started_at: datetime,
    ) -> None:
        conn.execute(
            "INSERT INTO intel_source_runs (run_id, source_id, status, started_at) "
            "VALUES (?, ?, 'running', ?)",
            (run_id, source_id, iso(started_at)),
        )

    def finish_source_run(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        source_id: str,
        *,
        status: str,
        outcome: str | None,
        complete: bool,
        truncated: bool,
        truncation_reason: str | None,
        new_resources: int = 0,
        refreshed: int = 0,
        backfilled: int = 0,
        filtered: int = 0,
        new_signals: int = 0,
        error_category: str | None = None,
        error_code: str | None = None,
        error: str | None = None,
        diagnostics: list[PollDiagnostic] | None = None,
        request_count: int = 0,
        page_count: int = 0,
        provider_item_count: int | None = None,
        next_due_at: datetime | None = None,
    ) -> None:
        conn.execute(
            """
            UPDATE intel_source_runs SET
              status=?, outcome=?, finished_at=datetime('now'), complete=?, truncated=?,
              truncation_reason=?, new_resources=?, refreshed=?, backfilled=?, filtered=?,
              new_signals=?, error_category=?, error_code=?, error=?, diagnostics_json=?,
              request_count=?, page_count=?, provider_item_count=?, next_due_at=?
            WHERE run_id=? AND source_id=?
            """,
            (
                status,
                outcome,
                int(complete),
                int(truncated),
                truncation_reason,
                new_resources,
                refreshed,
                backfilled,
                filtered,
                new_signals,
                error_category,
                error_code,
                error,
                diagnostics_json(diagnostics or []),
                request_count,
                page_count,
                provider_item_count,
                iso(next_due_at),
                run_id,
                source_id,
            ),
        )

    def list_source_runs(
        self, conn: sqlite3.Connection, source_id: str, *, limit: int = 20
    ) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM intel_source_runs WHERE source_id = ? "
            "ORDER BY started_at DESC LIMIT ?",
            (source_id, limit),
        ).fetchall()
        return [source_run_dict(row) for row in rows]

    def list_runs(self, conn: sqlite3.Connection, *, limit: int = 50) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM intel_crawl_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [crawl_run_dict(row) for row in rows]

    def get_run(self, conn: sqlite3.Connection, run_id: str) -> dict | None:
        row = conn.execute("SELECT * FROM intel_crawl_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        result = crawl_run_dict(row)
        source_rows = conn.execute(
            "SELECT * FROM intel_source_runs WHERE run_id = ? ORDER BY source_id", (run_id,)
        ).fetchall()
        result["sources"] = [source_run_dict(item) for item in source_rows]
        return result

    def finish_run(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        *,
        status: RunStatus,
        source_count: int,
        resource_count: int,
        signal_count: int,
        summary: dict,
        error: str | None = None,
    ) -> None:
        conn.execute(
            """
            UPDATE intel_crawl_runs SET status = ?, finished_at = datetime('now'),
              source_count = ?, resource_count = ?, signal_count = ?, summary_json = ?, error = ?
            WHERE id = ?
            """,
            (status, source_count, resource_count, signal_count, to_json(summary), error, run_id),
        )
