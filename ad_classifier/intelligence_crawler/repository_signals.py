"""Campaign-group, signal, and signal-evidence persistence."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ad_classifier.entity_graph.rows import to_json
from ad_classifier.intelligence_crawler.ids import campaign_group_id, evidence_id
from ad_classifier.intelligence_crawler.models import IntelEvidence, IntelSignal
from ad_classifier.intelligence_crawler.repository_rows import signal as signal_from_row
from ad_classifier.intelligence_crawler.timeutils import iso, parse_iso


class SignalRepositoryMixin:
    def get_or_create_campaign_group(
        self,
        conn: sqlite3.Connection,
        *,
        brand_name: str,
        group_key: str,
        title: str | None,
        now: datetime,
    ) -> str:
        group_id = campaign_group_id(brand_name, group_key)
        conn.execute(
            """
            INSERT INTO intel_campaign_groups
              (id, brand_name, group_key, title, first_seen_at, last_activity_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'candidate')
            ON CONFLICT(brand_name, group_key) DO UPDATE SET
              last_activity_at = excluded.last_activity_at,
              title = COALESCE(intel_campaign_groups.title, excluded.title)
            """,
            (group_id, brand_name, group_key, title, iso(now), iso(now)),
        )
        return group_id

    def group_signal_count(self, conn: sqlite3.Connection, group_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM intel_signals WHERE campaign_group_id = ?", (group_id,)
        ).fetchone()
        return int(row["n"] or 0)

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
                "UPDATE intel_signals SET last_seen_at = ?, updated_at = datetime('now') "
                "WHERE id = ?",
                (iso(signal.last_seen_at), signal.id),
            )
            return False
        for evidence in signal.evidence:
            conn.execute(
                """
                INSERT OR IGNORE INTO intel_signal_evidence
                  (id, signal_id, resource_id, source_id, evidence_type, url, text,
                   published_at, confidence)
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
        return [signal_from_row(row) for row in rows]

    def get_signal(self, conn: sqlite3.Connection, signal_id: str) -> IntelSignal | None:
        row = conn.execute("SELECT * FROM intel_signals WHERE id = ?", (signal_id,)).fetchone()
        return signal_from_row(row) if row else None

    def evidence_urls_for(
        self, conn: sqlite3.Connection, signal_ids: list[str]
    ) -> dict[str, list[str]]:
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
