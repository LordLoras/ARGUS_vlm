"""Persistence for the intelligence crawler. Writes only to ``intelligence_crawler.db``."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ad_classifier.entity_graph.rows import loads_dict, to_json
from ad_classifier.intelligence_crawler.models import (
    IntelArtifactSummary,
    IntelBrandOverview,
    IntelSource,
    IntelSourceStatus,
    ProviderCircuit,
    SourceState,
)
from ad_classifier.intelligence_crawler.repository_ledger import LedgerRepositoryMixin
from ad_classifier.intelligence_crawler.repository_resources import ResourceRepositoryMixin
from ad_classifier.intelligence_crawler.repository_rows import (
    artifact_summary as _artifact_summary_from_metadata,
)
from ad_classifier.intelligence_crawler.repository_rows import (
    coerce as _coerce,
)
from ad_classifier.intelligence_crawler.repository_rows import (
    diagnostics_json as _diagnostics_json,
)
from ad_classifier.intelligence_crawler.repository_rows import (
    max_datetime as _max_datetime,
)
from ad_classifier.intelligence_crawler.repository_rows import (
    merge_artifact_summary as _merge_artifact_summary,
)
from ad_classifier.intelligence_crawler.repository_rows import (
    source as _source,
)
from ad_classifier.intelligence_crawler.repository_rows import (
    source_run_dict as _source_run_dict,
)
from ad_classifier.intelligence_crawler.repository_rows import (
    state as _state,
)
from ad_classifier.intelligence_crawler.repository_runtime import RuntimeRepositoryMixin
from ad_classifier.intelligence_crawler.repository_signals import SignalRepositoryMixin
from ad_classifier.intelligence_crawler.schema import initialize_intelligence_crawler_db
from ad_classifier.intelligence_crawler.timeutils import as_utc, iso, parse_iso

SQLITE_BUSY_TIMEOUT_MS = 30_000


class IntelRepository(
    RuntimeRepositoryMixin,
    LedgerRepositoryMixin,
    ResourceRepositoryMixin,
    SignalRepositoryMixin,
):
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.expanduser().resolve()
        initialize_intelligence_crawler_db(self.db_path)

    @contextmanager
    def connect(self, *, readonly: bool = False) -> Generator[sqlite3.Connection, None, None]:
        if readonly:
            conn = sqlite3.connect(
                self.db_path.as_uri() + "?mode=ro",
                uri=True,
                check_same_thread=False,
                timeout=SQLITE_BUSY_TIMEOUT_MS / 1000,
            )
        else:
            conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000
            )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
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
                  archived_at=NULL,
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
            self._ensure_state_row(conn, source.id)

    def seed_sources(self, conn: sqlite3.Connection, sources: list[IntelSource]) -> None:
        """Refresh config seed sources without overwriting DB-curated enabled state."""
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
                  poll_interval_hours=excluded.poll_interval_hours,
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
            self._ensure_state_row(conn, source.id)

    def get_source(self, conn: sqlite3.Connection, source_id: str) -> IntelSource | None:
        row = conn.execute(
            "SELECT * FROM intel_sources WHERE id = ? AND archived_at IS NULL", (source_id,)
        ).fetchone()
        return _source(row) if row else None

    def list_sources(
        self,
        conn: sqlite3.Connection,
        *,
        enabled_only: bool = False,
        brand: str | None = None,
        due_at: datetime | None = None,
        include_archived: bool = False,
    ) -> list[IntelSource]:
        clauses: list[str] = []
        params: list[object] = []
        if not include_archived:
            clauses.append("s.archived_at IS NULL")
        if enabled_only:
            clauses.append("s.enabled = 1")
        if brand:
            clauses.append("LOWER(s.brand_name) = LOWER(?)")
            params.append(brand)
        if due_at is not None:
            clauses.extend(
                [
                    "(st.next_due_at IS NULL OR st.next_due_at <= ?)",
                    "(st.cooldown_until IS NULL OR st.cooldown_until <= ?)",
                ]
            )
            params.extend([iso(due_at), iso(due_at)])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = conn.execute(
            f"SELECT s.* FROM intel_sources s "
            f"LEFT JOIN intel_source_state st ON st.source_id = s.id "
            f"{where} ORDER BY s.brand_name, s.id",
            params,
        ).fetchall()
        return [_source(row) for row in rows]

    def list_brand_overviews(
        self, conn: sqlite3.Connection, *, query: str | None = None, limit: int = 100
    ) -> list[IntelBrandOverview]:
        pattern = f"%{query.strip()}%" if query and query.strip() else None
        brands: dict[str, dict] = {}

        def get_brand(name: str) -> dict:
            return brands.setdefault(
                name,
                {
                    "brand_name": name,
                    "source_count": 0,
                    "enabled_source_count": 0,
                    "resource_count": 0,
                    "backfill_resource_count": 0,
                    "signal_count": 0,
                    "latest_resource_seen_at": None,
                    "latest_signal_seen_at": None,
                    "source_types": set(),
                    "artifact_summary": IntelArtifactSummary(),
                },
            )

        where = "WHERE archived_at IS NULL"
        params: list[object] = []
        if pattern:
            where += " AND LOWER(brand_name) LIKE LOWER(?)"
            params.append(pattern)
        source_rows = conn.execute(
            f"SELECT brand_name, source_type, enabled FROM intel_sources {where}", params
        ).fetchall()
        for row in source_rows:
            brand = get_brand(str(row["brand_name"]))
            brand["source_count"] += 1
            brand["enabled_source_count"] += int(row["enabled"] or 0)
            brand["source_types"].add(str(row["source_type"]))

        resource_where = "WHERE LOWER(s.brand_name) LIKE LOWER(?)" if pattern else ""
        resource_rows = conn.execute(
            f"""
            SELECT s.brand_name, r.first_seen_at, r.is_backfill, r.metadata_json
            FROM intel_resources r
            JOIN intel_sources s ON s.id = r.source_id
            {resource_where}
            """,
            params,
        ).fetchall()
        for row in resource_rows:
            brand = get_brand(str(row["brand_name"]))
            brand["resource_count"] += 1
            brand["backfill_resource_count"] += int(row["is_backfill"] or 0)
            seen_at = parse_iso(row["first_seen_at"])
            brand["latest_resource_seen_at"] = _max_datetime(
                brand["latest_resource_seen_at"], seen_at
            )
            summary = _artifact_summary_from_metadata(loads_dict(row["metadata_json"]) or {})
            brand["artifact_summary"] = _merge_artifact_summary(brand["artifact_summary"], summary)

        media_where = "WHERE LOWER(s.brand_name) LIKE LOWER(?)" if pattern else ""
        media_rows = conn.execute(
            f"""
            SELECT s.brand_name, COUNT(*) AS media_assets
            FROM intel_media_assets a
            JOIN intel_resources r ON r.id = a.resource_id
            JOIN intel_sources s ON s.id = r.source_id
            {media_where}
            GROUP BY s.brand_name
            """,
            params,
        ).fetchall()
        for row in media_rows:
            brand = get_brand(str(row["brand_name"]))
            summary = brand["artifact_summary"]
            brand["artifact_summary"] = summary.model_copy(
                update={"media_asset_count": int(row["media_assets"] or 0)}
            )

        signal_where = "WHERE LOWER(brand_name) LIKE LOWER(?)" if pattern else ""
        signal_rows = conn.execute(
            f"SELECT brand_name, first_seen_at FROM intel_signals {signal_where}", params
        ).fetchall()
        for row in signal_rows:
            brand = get_brand(str(row["brand_name"]))
            brand["signal_count"] += 1
            seen_at = parse_iso(row["first_seen_at"])
            brand["latest_signal_seen_at"] = _max_datetime(brand["latest_signal_seen_at"], seen_at)

        overviews = []
        for value in brands.values():
            value["source_types"] = sorted(value["source_types"])
            overviews.append(IntelBrandOverview.model_validate(value))
        overviews.sort(
            key=lambda item: (
                iso(item.latest_resource_seen_at or item.latest_signal_seen_at) or "",
                item.resource_count,
            ),
            reverse=True,
        )
        return overviews[:limit]

    def set_source_enabled(self, conn: sqlite3.Connection, source_id: str, enabled: bool) -> None:
        conn.execute(
            "UPDATE intel_sources SET enabled = ?, updated_at = datetime('now') WHERE id = ?",
            (int(enabled), source_id),
        )

    def list_source_statuses(
        self, conn: sqlite3.Connection, *, brand: str | None = None
    ) -> list[IntelSourceStatus]:
        sources = self.list_sources(conn, brand=brand)
        if not sources:
            return []
        source_ids = [source.id for source in sources]
        placeholders = ",".join("?" for _ in source_ids)
        state_rows = conn.execute(
            f"SELECT * FROM intel_source_state WHERE source_id IN ({placeholders})", source_ids
        ).fetchall()
        states = {str(row["source_id"]): _state(row) for row in state_rows}
        run_rows = conn.execute(
            f"""
            SELECT sr.* FROM intel_source_runs sr
            JOIN (
              SELECT source_id, MAX(started_at) AS started_at
              FROM intel_source_runs
              WHERE source_id IN ({placeholders})
              GROUP BY source_id
            ) latest
              ON latest.source_id = sr.source_id AND latest.started_at = sr.started_at
            """,
            source_ids,
        ).fetchall()
        latest_runs = {str(row["source_id"]): _source_run_dict(row) for row in run_rows}
        return [
            IntelSourceStatus(
                source=source,
                state=states.get(source.id, SourceState(source_id=source.id)),
                recent_runs=([latest_runs[source.id]] if source.id in latest_runs else []),
                provider_circuit=self.get_provider_circuit(conn, source.source_type),
                resume_available=(
                    source.source_type == "google_atc" and _resume_checkpoint(states.get(source.id))
                ),
                resume_page=(
                    _resume_page(states.get(source.id))
                    if source.source_type == "google_atc"
                    else None
                ),
            )
            for source in sources
        ]

    def delete_source(self, conn: sqlite3.Connection, source_id: str) -> bool:
        cur = conn.execute(
            "UPDATE intel_sources SET enabled = 0, archived_at = datetime('now'), "
            "updated_at = datetime('now') WHERE id = ? AND archived_at IS NULL",
            (source_id,),
        )
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
        row = conn.execute(
            "SELECT * FROM intel_source_state WHERE source_id = ?", (source_id,)
        ).fetchone()
        return _state(row) if row is not None else SourceState(source_id=source_id)

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
            "last_outcome",
            "last_error_category",
            "last_error_code",
            "cooldown_until",
            "diagnostics_json",
            "state_json",
        }
        sets = []
        values: list[object] = []
        for key, value in fields.items():
            if key not in columns:
                raise KeyError(f"unknown source_state field: {key}")
            sets.append(f"{key} = ?")
            if key == "diagnostics_json":
                values.append(_diagnostics_json(value))
            elif key == "state_json":
                values.append(to_json(value or {}))
            else:
                values.append(_coerce(value))
        values.append(source_id)
        conn.execute(f"UPDATE intel_source_state SET {', '.join(sets)} WHERE source_id = ?", values)

    def get_provider_circuit(
        self, conn: sqlite3.Connection, source_type: str, *, now: datetime | None = None
    ) -> ProviderCircuit | None:
        now_value = iso(now or datetime.now(UTC))
        row = conn.execute(
            """
            SELECT st.source_id, st.cooldown_until, st.last_error_category,
                   st.last_error_code, st.last_error
            FROM intel_source_state st
            JOIN intel_sources s ON s.id = st.source_id
            WHERE s.source_type = ? AND s.archived_at IS NULL
              AND st.last_error_category IN ('rate_limited', 'blocked')
              AND st.cooldown_until IS NOT NULL AND st.cooldown_until > ?
            ORDER BY st.cooldown_until DESC LIMIT 1
            """,
            (source_type, now_value),
        ).fetchone()
        if row is None:
            return None
        return ProviderCircuit(
            provider=source_type,
            open_until=parse_iso(row["cooldown_until"]),
            source_id=str(row["source_id"]),
            error_code=str(row["last_error_code"] or "provider_circuit_open"),
            category=row["last_error_category"],
            message=row["last_error"],
        )

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
        now_utc = as_utc(now)
        assert now_utc is not None
        new_until = now_utc + timedelta(seconds=ttl_seconds)
        cur = conn.execute(
            "UPDATE intel_source_state SET lease_until = ?, lease_owner = ? "
            "WHERE source_id = ? AND (lease_until IS NULL OR lease_until <= ?)",
            (iso(new_until), owner, source_id, iso(now_utc)),
        )
        return cur.rowcount == 1

    def renew_lease(
        self,
        conn: sqlite3.Connection,
        source_id: str,
        owner: str,
        *,
        now: datetime,
        ttl_seconds: int,
    ) -> bool:
        now_utc = as_utc(now)
        assert now_utc is not None
        cur = conn.execute(
            "UPDATE intel_source_state SET lease_until = ? WHERE source_id = ? AND lease_owner = ?",
            (iso(now_utc + timedelta(seconds=ttl_seconds)), source_id, owner),
        )
        return cur.rowcount == 1

    def release_lease(self, conn: sqlite3.Connection, source_id: str, owner: str) -> None:
        conn.execute(
            "UPDATE intel_source_state SET lease_until = NULL, lease_owner = NULL "
            "WHERE source_id = ? AND lease_owner = ?",
            (source_id, owner),
        )

    def _ensure_state_row(self, conn: sqlite3.Connection, source_id: str) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO intel_source_state (source_id) VALUES (?)", (source_id,)
        )


def _resume_checkpoint(state: SourceState | None) -> bool:
    google = state.provider_state.get("google_atc", {}) if state else {}
    return bool(isinstance(google, dict) and google.get("checkpoint", {}).get("token"))


def _resume_page(state: SourceState | None) -> int | None:
    google = state.provider_state.get("google_atc", {}) if state else {}
    checkpoint = google.get("checkpoint", {}) if isinstance(google, dict) else {}
    try:
        return int(checkpoint["page_count"]) if checkpoint.get("token") else None
    except (TypeError, ValueError):
        return None
