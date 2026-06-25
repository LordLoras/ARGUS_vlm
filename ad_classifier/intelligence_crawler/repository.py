"""Persistence for the intelligence crawler. Writes only to ``intelligence_crawler.db``."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from ad_classifier.entity_graph.rows import loads_dict, loads_list, to_json
from ad_classifier.intelligence_crawler.ids import campaign_group_id, evidence_id
from ad_classifier.intelligence_crawler.models import (
    IntelEvidence,
    IntelResource,
    IntelSignal,
    IntelSource,
    RunStatus,
    SourceState,
)
from ad_classifier.intelligence_crawler.schema import initialize_intelligence_crawler_db
from ad_classifier.intelligence_crawler.timeutils import as_utc, iso, parse_iso


class IntelRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.expanduser().resolve()
        initialize_intelligence_crawler_db(self.db_path)

    @contextmanager
    def connect(self, *, readonly: bool = False) -> Generator[sqlite3.Connection, None, None]:
        if readonly:
            conn = sqlite3.connect(
                self.db_path.as_uri() + "?mode=ro", uri=True, check_same_thread=False
            )
        else:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if readonly:
            conn.execute("PRAGMA query_only = ON")
        try:
            yield conn
        finally:
            conn.close()

    # ---- sources ---------------------------------------------------------------

    def sync_sources(self, conn: sqlite3.Connection, sources: list[IntelSource]) -> None:
        """Upsert config sources. Preserves ``source_activated_at`` already set in the DB."""
        for source in sources:
            conn.execute(
                """
                INSERT INTO intel_sources
                  (id, brand_name, market, source_type, tier, url, platform, platform_id,
                   enabled, poll_interval_hours, allowed_domains_json, config_json, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                  brand_name=excluded.brand_name, market=excluded.market,
                  source_type=excluded.source_type, tier=excluded.tier, url=excluded.url,
                  platform=excluded.platform, platform_id=excluded.platform_id,
                  enabled=excluded.enabled, poll_interval_hours=excluded.poll_interval_hours,
                  allowed_domains_json=excluded.allowed_domains_json,
                  config_json=excluded.config_json, notes=excluded.notes,
                  updated_at=datetime('now')
                """,
                (
                    source.id,
                    source.brand_name,
                    source.market,
                    source.source_type,
                    source.tier,
                    source.url,
                    source.platform,
                    source.platform_id,
                    int(source.enabled),
                    source.poll_interval_hours,
                    to_json(source.allowed_domains),
                    to_json(source.config),
                    source.notes,
                ),
            )

    def get_source(self, conn: sqlite3.Connection, source_id: str) -> IntelSource | None:
        row = conn.execute("SELECT * FROM intel_sources WHERE id = ?", (source_id,)).fetchone()
        return _source(row) if row else None

    def list_sources(
        self,
        conn: sqlite3.Connection,
        *,
        enabled_only: bool = False,
        brand: str | None = None,
    ) -> list[IntelSource]:
        clauses: list[str] = []
        params: list[object] = []
        if enabled_only:
            clauses.append("enabled = 1")
        if brand:
            clauses.append("LOWER(brand_name) = LOWER(?)")
            params.append(brand)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM intel_sources {where} ORDER BY brand_name, id", params
        ).fetchall()
        return [_source(row) for row in rows]

    def set_source_enabled(self, conn: sqlite3.Connection, source_id: str, enabled: bool) -> None:
        conn.execute(
            "UPDATE intel_sources SET enabled = ?, updated_at = datetime('now') WHERE id = ?",
            (int(enabled), source_id),
        )

    def delete_source(self, conn: sqlite3.Connection, source_id: str) -> bool:
        cur = conn.execute("DELETE FROM intel_sources WHERE id = ?", (source_id,))
        return cur.rowcount > 0

    def set_source_activated(
        self, conn: sqlite3.Connection, source_id: str, activated_at: datetime
    ) -> None:
        conn.execute(
            "UPDATE intel_sources SET source_activated_at = ?, updated_at = datetime('now') "
            "WHERE id = ? AND source_activated_at IS NULL",
            (iso(activated_at), source_id),
        )

    # ---- source state + lease --------------------------------------------------

    def get_source_state(self, conn: sqlite3.Connection, source_id: str) -> SourceState:
        self._ensure_state_row(conn, source_id)
        row = conn.execute(
            "SELECT * FROM intel_source_state WHERE source_id = ?", (source_id,)
        ).fetchone()
        return _state(row)

    def update_source_state(self, conn: sqlite3.Connection, source_id: str, **fields) -> None:
        if not fields:
            return
        self._ensure_state_row(conn, source_id)
        columns = {
            "watermark",
            "etag",
            "last_modified",
            "last_attempt_at",
            "last_success_at",
            "last_error",
            "consecutive_errors",
            "next_due_at",
        }
        sets = []
        values: list[object] = []
        for key, value in fields.items():
            if key not in columns:
                raise KeyError(f"unknown source_state field: {key}")
            sets.append(f"{key} = ?")
            values.append(_coerce(value))
        values.append(source_id)
        conn.execute(f"UPDATE intel_source_state SET {', '.join(sets)} WHERE source_id = ?", values)

    def acquire_lease(
        self,
        conn: sqlite3.Connection,
        source_id: str,
        owner: str,
        *,
        now: datetime,
        ttl_seconds: int,
    ) -> bool:
        self._ensure_state_row(conn, source_id)
        row = conn.execute(
            "SELECT lease_until, lease_owner FROM intel_source_state WHERE source_id = ?",
            (source_id,),
        ).fetchone()
        lease_until = parse_iso(row["lease_until"])
        now_utc = as_utc(now)
        assert now_utc is not None
        if lease_until is not None and lease_until > now_utc and row["lease_owner"] != owner:
            return False
        new_until = now_utc + timedelta(seconds=ttl_seconds)
        conn.execute(
            "UPDATE intel_source_state SET lease_until = ?, lease_owner = ? WHERE source_id = ?",
            (iso(new_until), owner, source_id),
        )
        return True

    def release_lease(self, conn: sqlite3.Connection, source_id: str) -> None:
        conn.execute(
            "UPDATE intel_source_state SET lease_until = NULL, lease_owner = NULL WHERE source_id = ?",
            (source_id,),
        )

    def _ensure_state_row(self, conn: sqlite3.Connection, source_id: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO intel_source_state (source_id) VALUES (?)", (source_id,)
        )

    # ---- resources -------------------------------------------------------------

    def existing_resource_ids(self, conn: sqlite3.Connection, source_id: str) -> set[str]:
        rows = conn.execute(
            "SELECT id FROM intel_resources WHERE source_id = ?", (source_id,)
        ).fetchall()
        return {str(row["id"]) for row in rows}

    def insert_resource(self, conn: sqlite3.Connection, resource: IntelResource) -> bool:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO intel_resources
              (id, source_id, run_id, resource_type, url, canonical_url, platform, platform_id,
               content_hash, title, description, published_at, first_seen_at, fetched_at,
               is_backfill, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resource.id,
                resource.source_id,
                resource.run_id,
                resource.resource_type,
                resource.url,
                resource.canonical_url,
                resource.platform,
                resource.platform_id,
                resource.content_hash,
                resource.title,
                resource.description,
                iso(resource.published_at),
                iso(resource.first_seen_at),
                iso(resource.fetched_at),
                int(resource.is_backfill),
                to_json(resource.metadata),
            ),
        )
        return cur.rowcount > 0

    # ---- campaign groups -------------------------------------------------------

    def get_or_create_campaign_group(
        self,
        conn: sqlite3.Connection,
        *,
        brand_name: str,
        group_key: str,
        title: str | None,
        now: datetime,
    ) -> str:
        gid = campaign_group_id(brand_name, group_key)
        conn.execute(
            """
            INSERT INTO intel_campaign_groups
              (id, brand_name, group_key, title, first_seen_at, last_activity_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'candidate')
            ON CONFLICT(brand_name, group_key) DO UPDATE SET
              last_activity_at = excluded.last_activity_at,
              title = COALESCE(intel_campaign_groups.title, excluded.title)
            """,
            (gid, brand_name, group_key, title, iso(now), iso(now)),
        )
        return gid

    def group_signal_count(self, conn: sqlite3.Connection, group_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM intel_signals WHERE campaign_group_id = ?", (group_id,)
        ).fetchone()
        return int(row["n"] or 0)

    # ---- signals ---------------------------------------------------------------

    def insert_signal(self, conn: sqlite3.Connection, signal: IntelSignal) -> bool:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO intel_signals
              (id, brand_name, campaign_group_id, signal_type, status, confidence, title,
               summary, campaign_name, products_json, first_seen_at, source_published_at,
               last_seen_at, score_breakdown_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal.id,
                signal.brand_name,
                signal.campaign_group_id,
                signal.signal_type,
                signal.status,
                signal.confidence,
                signal.title,
                signal.summary,
                signal.campaign_name,
                to_json(signal.products),
                iso(signal.first_seen_at),
                iso(signal.source_published_at),
                iso(signal.last_seen_at),
                to_json(signal.score_breakdown),
            ),
        )
        if cur.rowcount == 0:
            conn.execute(
                "UPDATE intel_signals SET last_seen_at = ?, updated_at = datetime('now') WHERE id = ?",
                (iso(signal.last_seen_at), signal.id),
            )
            return False
        for evidence in signal.evidence:
            conn.execute(
                """
                INSERT OR IGNORE INTO intel_signal_evidence
                  (id, signal_id, resource_id, source_id, evidence_type, url, text, published_at, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.id or evidence_id(signal.id, evidence.resource_id),
                    signal.id,
                    evidence.resource_id,
                    evidence.source_id,
                    evidence.evidence_type,
                    evidence.url,
                    evidence.text,
                    iso(evidence.published_at),
                    evidence.confidence,
                ),
            )
        return True

    def list_signals(
        self,
        conn: sqlite3.Connection,
        *,
        brand: str | None = None,
        since: datetime | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[IntelSignal]:
        clauses: list[str] = []
        params: list[object] = []
        if brand:
            clauses.append("LOWER(brand_name) = LOWER(?)")
            params.append(brand)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if since is not None:
            clauses.append("COALESCE(source_published_at, first_seen_at) >= ?")
            params.append(iso(since))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM intel_signals {where} "
            f"ORDER BY COALESCE(source_published_at, first_seen_at) DESC LIMIT ?",
            params,
        ).fetchall()
        return [_signal(row) for row in rows]

    def get_signal(self, conn: sqlite3.Connection, signal_id: str) -> IntelSignal | None:
        row = conn.execute("SELECT * FROM intel_signals WHERE id = ?", (signal_id,)).fetchone()
        return _signal(row) if row else None

    def evidence_urls_for(
        self, conn: sqlite3.Connection, signal_ids: list[str]
    ) -> dict[str, list[str]]:
        """Bulk-fetch evidence URLs keyed by signal id (for digests / detail views)."""
        if not signal_ids:
            return {}
        placeholders = ",".join("?" * len(signal_ids))
        rows = conn.execute(
            f"SELECT signal_id, url FROM intel_signal_evidence "
            f"WHERE signal_id IN ({placeholders}) AND url IS NOT NULL",
            signal_ids,
        ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(str(row["signal_id"]), []).append(str(row["url"]))
        return result

    def evidence_for(self, conn: sqlite3.Connection, signal_id: str) -> list[IntelEvidence]:
        rows = conn.execute(
            "SELECT * FROM intel_signal_evidence WHERE signal_id = ?", (signal_id,)
        ).fetchall()
        return [
            IntelEvidence(
                id=row["id"],
                signal_id=row["signal_id"],
                resource_id=row["resource_id"],
                source_id=row["source_id"],
                evidence_type=row["evidence_type"],
                url=row["url"],
                text=row["text"],
                published_at=parse_iso(row["published_at"]),
                confidence=float(row["confidence"] or 0.0),
            )
            for row in rows
        ]

    # ---- runs ------------------------------------------------------------------

    def create_run(self, conn: sqlite3.Connection, run_id: str) -> None:
        conn.execute("INSERT INTO intel_crawl_runs (id, status) VALUES (?, 'running')", (run_id,))

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


def _coerce(value: object) -> object:
    return iso(value) if isinstance(value, datetime) else value


def _source(row: sqlite3.Row) -> IntelSource:
    return IntelSource(
        id=row["id"],
        brand_name=row["brand_name"],
        market=row["market"],
        source_type=row["source_type"],
        tier=row["tier"],
        url=row["url"],
        platform=row["platform"],
        platform_id=row["platform_id"],
        enabled=bool(row["enabled"]),
        poll_interval_hours=float(row["poll_interval_hours"] or 12.0),
        source_activated_at=parse_iso(row["source_activated_at"]),
        allowed_domains=[str(x) for x in (loads_list(row["allowed_domains_json"]) or [])],
        config=loads_dict(row["config_json"]) or {},
        notes=row["notes"],
    )


def _state(row: sqlite3.Row) -> SourceState:
    return SourceState(
        source_id=row["source_id"],
        last_attempt_at=parse_iso(row["last_attempt_at"]),
        last_success_at=parse_iso(row["last_success_at"]),
        next_due_at=parse_iso(row["next_due_at"]),
        last_error=row["last_error"],
        consecutive_errors=int(row["consecutive_errors"] or 0),
        etag=row["etag"],
        last_modified=row["last_modified"],
        watermark=row["watermark"],
        lease_until=parse_iso(row["lease_until"]),
        lease_owner=row["lease_owner"],
    )


def _signal(row: sqlite3.Row) -> IntelSignal:
    return IntelSignal(
        id=row["id"],
        brand_name=row["brand_name"],
        campaign_group_id=row["campaign_group_id"],
        signal_type=row["signal_type"],
        status=row["status"],
        confidence=float(row["confidence"] or 0.0),
        title=row["title"],
        summary=row["summary"],
        campaign_name=row["campaign_name"],
        products=[str(x) for x in (loads_list(row["products_json"]) or [])],
        first_seen_at=_req_dt(row["first_seen_at"]),
        source_published_at=parse_iso(row["source_published_at"]),
        last_seen_at=_req_dt(row["last_seen_at"]),
        score_breakdown=loads_dict(row["score_breakdown_json"]) or {},
    )


def _req_dt(value: str | None) -> datetime:
    """Parse a NOT-NULL timestamp column; asserts presence for the type checker."""
    parsed = parse_iso(value)
    assert parsed is not None
    return parsed
