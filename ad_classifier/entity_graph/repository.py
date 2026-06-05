from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ad_classifier.entity_graph import rows
from ad_classifier.entity_graph.crawler_config import EntityCrawlerConfig, product_resolution_key
from ad_classifier.entity_graph.models import (
    AdChangeSuggestion,
    AdChangeSuggestionStatus,
    EntityAlias,
    EntityEdge,
    EntityNode,
    EntityObservation,
    EntitySource,
    EntityStatus,
    EntityType,
    GraphPayload,
    ProductPage,
    ProductSummary,
    TaxonomyMapping,
    TaxonomyMappingSummary,
)
from ad_classifier.entity_graph.schema import initialize_entity_graph_db
from ad_classifier.entity_graph.utils import (
    edge_id,
    mapping_id,
    merge_status,
    node_id,
    normalize_name,
    observation_id,
    suggestion_id,
)
from ad_classifier.entity_graph.utils import (
    source_id as make_source_id,
)


class EntityGraphRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.expanduser().resolve()
        initialize_entity_graph_db(self.db_path)

    @contextmanager
    def connect(self, *, readonly: bool = False) -> Generator[sqlite3.Connection, None, None]:
        if readonly:
            uri = self.db_path.as_uri() + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
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

    def upsert_source(
        self,
        conn: sqlite3.Connection,
        *,
        source_type: str,
        label: str,
        url: str | None = None,
        ad_id: str | None = None,
        payload: dict | None = None,
        source_id: str | None = None,
    ) -> EntitySource:
        sid = source_id or make_source_id(source_type, label, url, ad_id)
        conn.execute(
            """
            INSERT INTO entity_sources (id, source_type, label, url, ad_id, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              label = excluded.label,
              url = excluded.url,
              ad_id = excluded.ad_id,
              payload_json = excluded.payload_json
            """,
            (sid, source_type, label, url, ad_id, rows.to_json(payload)),
        )
        return self.get_source(conn, sid)

    def get_source(self, conn: sqlite3.Connection, source_id: str) -> EntitySource:
        row = conn.execute("SELECT * FROM entity_sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise KeyError(source_id)
        return rows.source(row)

    def upsert_node(
        self,
        conn: sqlite3.Connection,
        *,
        entity_type: EntityType,
        canonical_name: str,
        status: EntityStatus,
        confidence: float,
        description: str | None = None,
        generated_from: dict | None = None,
    ) -> tuple[EntityNode, bool]:
        normalized = normalize_name(canonical_name)
        if not normalized:
            raise ValueError("entity canonical name is empty")
        existing = conn.execute(
            "SELECT * FROM entity_nodes WHERE type = ? AND normalized_name = ?",
            (entity_type, normalized),
        ).fetchone()
        if existing is None:
            new_node_id = node_id(entity_type, normalized)
            conn.execute(
                """
                INSERT INTO entity_nodes (
                  id, type, canonical_name, normalized_name, description,
                  status, confidence, generated_from_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_node_id,
                    entity_type,
                    canonical_name.strip(),
                    normalized,
                    description,
                    status,
                    confidence,
                    rows.to_json(generated_from),
                ),
            )
            return self.get_node(conn, new_node_id), True

        existing_node_id = str(existing["id"])
        next_status = merge_status(str(existing["status"]), status)
        next_confidence = max(float(existing["confidence"] or 0.0), confidence)
        next_description = description or existing["description"]
        next_generated = generated_from or rows.loads_dict(existing["generated_from_json"])
        conn.execute(
            """
            UPDATE entity_nodes
            SET canonical_name = ?,
                description = ?,
                status = ?,
                confidence = ?,
                generated_from_json = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                str(existing["canonical_name"]) or canonical_name.strip(),
                next_description,
                next_status,
                next_confidence,
                rows.to_json(next_generated),
                existing_node_id,
            ),
        )
        return self.get_node(conn, existing_node_id), False

    def get_node(self, conn: sqlite3.Connection, node_id: str) -> EntityNode:
        row = conn.execute("SELECT * FROM entity_nodes WHERE id = ?", (node_id,)).fetchone()
        if row is None:
            raise KeyError(node_id)
        return rows.node(row)

    def set_node_status(
        self, conn: sqlite3.Connection, node_id: str, status: EntityStatus
    ) -> EntityNode:
        conn.execute(
            "UPDATE entity_nodes SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, node_id),
        )
        return self.get_node(conn, node_id)

    def update_node_fields(
        self,
        conn: sqlite3.Connection,
        node_id: str,
        *,
        canonical_name: str | None = None,
        description: str | None = None,
        status: EntityStatus | None = None,
        confidence: float | None = None,
        generated_from: dict | None = None,
    ) -> EntityNode:
        current = self.get_node(conn, node_id)
        next_name = canonical_name.strip() if canonical_name is not None and canonical_name.strip() else current.canonical_name
        next_normalized = normalize_name(next_name)
        duplicate = conn.execute(
            """
            SELECT id
            FROM entity_nodes
            WHERE type = ? AND normalized_name = ? AND id <> ?
            """,
            (current.type, next_normalized, node_id),
        ).fetchone()
        if duplicate is not None:
            raise ValueError(f"{current.type} entity already exists for {next_name!r}")
        conn.execute(
            """
            UPDATE entity_nodes
            SET canonical_name = ?,
                normalized_name = ?,
                description = ?,
                status = ?,
                confidence = ?,
                generated_from_json = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                next_name,
                next_normalized,
                description if description is not None else current.description,
                status or current.status,
                confidence if confidence is not None else current.confidence,
                rows.to_json(generated_from or current.generated_from),
                node_id,
            ),
        )
        return self.get_node(conn, node_id)

    def replace_relation(
        self,
        conn: sqlite3.Connection,
        *,
        source_node_id: str,
        relation: str,
        entity_type: EntityType,
        canonical_name: str | None,
        source_id: str | None,
        status: EntityStatus = "confirmed_reviewed",
        confidence: float = 0.98,
    ) -> EntityNode | None:
        if canonical_name is not None and not canonical_name.strip():
            canonical_name = None
        conn.execute(
            """
            UPDATE entity_edges
            SET status = 'rejected'
            WHERE source_node_id = ? AND relation = ?
            """,
            (source_node_id, relation),
        )
        if canonical_name is None:
            return None
        target, _created = self.upsert_node(
            conn,
            entity_type=entity_type,
            canonical_name=canonical_name,
            status=status,
            confidence=confidence,
            generated_from={"source": "user_edit"},
        )
        self.upsert_edge(
            conn,
            source_node_id=source_node_id,
            target_node_id=target.id,
            relation=relation,
            confidence=confidence,
            status=status,
            source_id=source_id,
            evidence={"source": "user_edit"},
        )
        return target

    def clear_experimental_graph(self, conn: sqlite3.Connection) -> None:
        for table in (
            "taxonomy_mappings",
            "entity_observations",
            "entity_edges",
            "entity_aliases",
            "ad_change_suggestions",
            "entity_sources",
            "entity_nodes",
            "resolver_runs",
        ):
            conn.execute(f"DELETE FROM {table}")

    def upsert_ad_change_suggestion(
        self,
        conn: sqlite3.Connection,
        *,
        ad_id: str,
        source_id: str | None,
        field_path: str,
        current_value: str | None,
        suggested_value: str,
        confidence: float,
        reason: str,
        evidence_text: str | None,
        apply_safety: str,
        payload: dict | None = None,
    ) -> AdChangeSuggestion:
        sid = suggestion_id(ad_id, field_path, suggested_value, source_id)
        conn.execute(
            """
            INSERT INTO ad_change_suggestions (
              id, ad_id, source_id, field_path, current_value, suggested_value,
              confidence, reason, evidence_text, apply_safety, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ad_id, field_path, suggested_value, source_id) DO UPDATE SET
              current_value = excluded.current_value,
              confidence = max(ad_change_suggestions.confidence, excluded.confidence),
              reason = excluded.reason,
              evidence_text = excluded.evidence_text,
              apply_safety = excluded.apply_safety,
              payload_json = excluded.payload_json,
              status = CASE
                WHEN ad_change_suggestions.status IN ('approved', 'rejected', 'applied')
                THEN ad_change_suggestions.status
                ELSE 'pending'
              END
            """,
            (
                sid,
                ad_id,
                source_id,
                field_path,
                current_value,
                suggested_value,
                confidence,
                reason,
                evidence_text,
                apply_safety,
                rows.to_json(payload),
            ),
        )
        row = conn.execute("SELECT * FROM ad_change_suggestions WHERE id = ?", (sid,)).fetchone()
        return rows.suggestion(row)

    def list_ad_change_suggestions(
        self,
        conn: sqlite3.Connection,
        *,
        status: AdChangeSuggestionStatus | None = None,
        ad_id: str | None = None,
        limit: int = 200,
    ) -> list[AdChangeSuggestion]:
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if ad_id:
            clauses.append("ad_id = ?")
            params.append(ad_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        result = conn.execute(
            f"""
            SELECT *
            FROM ad_change_suggestions
            {where}
            ORDER BY
              CASE status
                WHEN 'pending' THEN 0
                WHEN 'approved' THEN 1
                WHEN 'applied' THEN 2
                ELSE 3
              END,
              confidence DESC,
              created_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [rows.suggestion(row) for row in result]

    def crawl_queue_metadata(self, conn: sqlite3.Connection, ad_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not ad_ids:
            return {}
        placeholders = ",".join("?" for _ in ad_ids)
        metadata = {
            ad_id: {"pending_suggestion_count": 0, "last_crawled_at": None}
            for ad_id in ad_ids
        }
        for row in conn.execute(
            f"""
            SELECT ad_id, COUNT(*) AS count
            FROM ad_change_suggestions
            WHERE status = 'pending' AND ad_id IN ({placeholders})
            GROUP BY ad_id
            """,
            ad_ids,
        ).fetchall():
            metadata[str(row["ad_id"])]["pending_suggestion_count"] = int(row["count"] or 0)
        for row in conn.execute(
            f"""
            SELECT ad_id, MAX(created_at) AS last_crawled_at
            FROM entity_sources
            WHERE source_type = 'discovery_only' AND ad_id IN ({placeholders})
            GROUP BY ad_id
            """,
            ad_ids,
        ).fetchall():
            metadata[str(row["ad_id"])]["last_crawled_at"] = row["last_crawled_at"]
        return metadata

    def lookup_nodes(
        self,
        conn: sqlite3.Connection,
        *,
        entity_type: EntityType,
        q: str | None = None,
        limit: int = 20,
    ) -> list[EntityNode]:
        clauses = ["type = ?", "status <> 'rejected'"]
        params: list[object] = [entity_type]
        if q:
            clauses.append("(canonical_name LIKE ? OR normalized_name LIKE ?)")
            params.extend([f"%{q}%", f"%{normalize_name(q)}%"])
        params.append(limit)
        rows_ = conn.execute(
            f"""
            SELECT *
            FROM entity_nodes
            WHERE {' AND '.join(clauses)}
            ORDER BY confidence DESC, canonical_name
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [rows.node(row) for row in rows_]

    def first_related(
        self,
        conn: sqlite3.Connection,
        source_id: str,
        relation: str,
    ) -> EntityNode | None:
        return _first_related(conn, source_id, relation)

    def get_ad_change_suggestion(
        self, conn: sqlite3.Connection, suggestion_id_: str
    ) -> AdChangeSuggestion:
        row = conn.execute(
            "SELECT * FROM ad_change_suggestions WHERE id = ?",
            (suggestion_id_,),
        ).fetchone()
        if row is None:
            raise KeyError(suggestion_id_)
        return rows.suggestion(row)

    def set_ad_change_suggestion_status(
        self,
        conn: sqlite3.Connection,
        suggestion_id_: str,
        status: AdChangeSuggestionStatus,
    ) -> AdChangeSuggestion:
        conn.execute(
            """
            UPDATE ad_change_suggestions
            SET status = ?,
                reviewed_at = coalesce(reviewed_at, datetime('now'))
            WHERE id = ?
            """,
            (status, suggestion_id_),
        )
        return self.get_ad_change_suggestion(conn, suggestion_id_)

    def mark_ad_change_suggestion_applied(
        self,
        conn: sqlite3.Connection,
        suggestion_id_: str,
        applied_value: str,
    ) -> AdChangeSuggestion:
        conn.execute(
            """
            UPDATE ad_change_suggestions
            SET status = 'applied',
                suggested_value = ?,
                reviewed_at = coalesce(reviewed_at, datetime('now')),
                applied_at = datetime('now')
            WHERE id = ?
            """,
            (applied_value, suggestion_id_),
        )
        return self.get_ad_change_suggestion(conn, suggestion_id_)

    def upsert_alias(
        self,
        conn: sqlite3.Connection,
        *,
        node_id: str,
        alias: str,
        source_id: str | None,
        status: EntityStatus,
        confidence: float,
    ) -> EntityAlias:
        normalized = normalize_name(alias)
        conn.execute(
            """
            INSERT INTO entity_aliases (
              node_id, alias, normalized_alias, source_id, confidence, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id, normalized_alias, source_id) DO UPDATE SET
              confidence = max(entity_aliases.confidence, excluded.confidence),
              status = excluded.status
            """,
            (node_id, alias.strip(), normalized, source_id, confidence, status),
        )
        row = conn.execute(
            """
            SELECT * FROM entity_aliases
            WHERE node_id = ? AND normalized_alias = ? AND source_id IS ?
            """,
            (node_id, normalized, source_id),
        ).fetchone()
        return rows.alias(row)

    def upsert_edge(
        self,
        conn: sqlite3.Connection,
        *,
        source_node_id: str,
        target_node_id: str,
        relation: str,
        confidence: float,
        status: EntityStatus,
        source_id: str | None,
        evidence: dict | None = None,
    ) -> EntityEdge:
        new_edge_id = edge_id(source_node_id, relation, target_node_id, source_id)
        conn.execute(
            """
            INSERT INTO entity_edges (
              id, source_node_id, target_node_id, relation, confidence,
              status, source_id, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_node_id, target_node_id, relation, source_id) DO UPDATE SET
              confidence = max(entity_edges.confidence, excluded.confidence),
              status = excluded.status,
              evidence_json = excluded.evidence_json
            """,
            (
                new_edge_id,
                source_node_id,
                target_node_id,
                relation,
                confidence,
                status,
                source_id,
                rows.to_json(evidence),
            ),
        )
        row = conn.execute("SELECT * FROM entity_edges WHERE id = ?", (new_edge_id,)).fetchone()
        return rows.edge(row)

    def upsert_observation(
        self,
        conn: sqlite3.Connection,
        *,
        node_id: str,
        ad_id: str,
        field: str,
        evidence_text: str,
        source: str,
        confidence: float,
        source_id: str | None,
        time_ms: int | None = None,
        frame_index: int | None = None,
    ) -> EntityObservation:
        if source_id and source in {"web_crawl", "web_vlm"}:
            existing = conn.execute(
                """
                SELECT id
                FROM entity_observations
                WHERE node_id = ?
                  AND ad_id = ?
                  AND field = ?
                  AND source = ?
                  AND source_id = ?
                ORDER BY created_at, id
                """,
                (node_id, ad_id, field, source, source_id),
            ).fetchall()
            if existing:
                existing_id = str(existing[0]["id"])
                conn.execute(
                    """
                    UPDATE entity_observations
                    SET evidence_text = ?,
                        confidence = max(confidence, ?),
                        time_ms = coalesce(time_ms, ?),
                        frame_index = coalesce(frame_index, ?)
                    WHERE id = ?
                    """,
                    (evidence_text, confidence, time_ms, frame_index, existing_id),
                )
                duplicate_ids = [str(row["id"]) for row in existing[1:]]
                if duplicate_ids:
                    placeholders = ",".join("?" for _ in duplicate_ids)
                    conn.execute(
                        f"DELETE FROM entity_observations WHERE id IN ({placeholders})",
                        duplicate_ids,
                    )
                row = conn.execute(
                    "SELECT * FROM entity_observations WHERE id = ?",
                    (existing_id,),
                ).fetchone()
                return rows.observation(row)

        obs_id = observation_id(node_id, ad_id, field, evidence_text, source)
        conn.execute(
            """
            INSERT INTO entity_observations (
              id, node_id, ad_id, field, evidence_text, source, time_ms,
              frame_index, confidence, source_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id, ad_id, field, evidence_text, source) DO UPDATE SET
              confidence = max(entity_observations.confidence, excluded.confidence),
              time_ms = coalesce(entity_observations.time_ms, excluded.time_ms),
              frame_index = coalesce(entity_observations.frame_index, excluded.frame_index)
            """,
            (
                obs_id,
                node_id,
                ad_id,
                field,
                evidence_text,
                source,
                time_ms,
                frame_index,
                confidence,
                source_id,
            ),
        )
        row = conn.execute("SELECT * FROM entity_observations WHERE id = ?", (obs_id,)).fetchone()
        return rows.observation(row)

    def upsert_taxonomy_mapping(
        self,
        conn: sqlite3.Connection,
        *,
        entity_id: str,
        taxonomy_type: str,
        taxonomy_id: str,
        taxonomy_name: str | None,
        confidence: float,
        status: EntityStatus,
        source_id: str | None,
        evidence_text: str | None = None,
    ) -> TaxonomyMapping:
        new_mapping_id = mapping_id(entity_id, taxonomy_type, taxonomy_id, source_id)
        conn.execute(
            """
            INSERT INTO taxonomy_mappings (
              id, entity_id, taxonomy_type, taxonomy_id, taxonomy_name,
              confidence, status, source_id, evidence_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id, taxonomy_type, taxonomy_id, source_id) DO UPDATE SET
              taxonomy_name = excluded.taxonomy_name,
              confidence = max(taxonomy_mappings.confidence, excluded.confidence),
              status = excluded.status,
              evidence_text = excluded.evidence_text
            """,
            (
                new_mapping_id,
                entity_id,
                taxonomy_type,
                taxonomy_id,
                taxonomy_name,
                confidence,
                status,
                source_id,
                evidence_text,
            ),
        )
        row = conn.execute("SELECT * FROM taxonomy_mappings WHERE id = ?", (new_mapping_id,)).fetchone()
        return rows.mapping(row)

    def list_products(
        self,
        conn: sqlite3.Connection,
        *,
        status: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
        crawler_config: EntityCrawlerConfig | None = None,
    ) -> list[ProductSummary]:
        clauses = ["type = 'product'"]
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if q:
            clauses.append("(canonical_name LIKE ? OR normalized_name LIKE ?)")
            params.extend([f"%{q}%", f"%{normalize_name(q)}%"])
        query_limit = limit
        query_offset = offset
        if crawler_config is not None:
            query_limit = min(max((limit + offset) * 8, 250), 2000)
            query_offset = 0
        result_rows = conn.execute(
            f"""
            SELECT * FROM entity_nodes
            WHERE {' AND '.join(clauses)}
            ORDER BY status DESC, canonical_name
            LIMIT ? OFFSET ?
            """,
            (*params, query_limit, query_offset),
        ).fetchall()
        summaries = [self._product_summary(conn, rows.node(row)) for row in result_rows]
        if crawler_config is not None:
            summaries = _dedupe_product_summaries(summaries, crawler_config)
            return summaries[offset : offset + limit]
        return summaries

    def get_product_page(self, conn: sqlite3.Connection, product_id: str) -> ProductPage | None:
        row = conn.execute(
            "SELECT * FROM entity_nodes WHERE id = ? AND type = 'product'", (product_id,)
        ).fetchone()
        if row is None:
            return None
        summary = self._product_summary(conn, rows.node(row))
        aliases = _dedupe_aliases(
            [
                rows.alias(item)
                for item in conn.execute(
                    """
                    SELECT * FROM entity_aliases
                    WHERE node_id = ?
                    ORDER BY normalized_alias, confidence DESC, status DESC, alias
                    """,
                    (product_id,),
                ).fetchall()
            ]
        )
        mappings = [
            rows.mapping(item)
            for item in conn.execute(
                "SELECT * FROM taxonomy_mappings WHERE entity_id = ? ORDER BY confidence DESC",
                (product_id,),
            ).fetchall()
        ]
        observations = [
            rows.observation(item)
            for item in conn.execute(
                """
                SELECT * FROM entity_observations
                WHERE node_id = ?
                ORDER BY ad_id, coalesce(time_ms, 0)
                """,
                (product_id,),
            ).fetchall()
        ]
        return ProductPage(
            **summary.model_dump(),
            aliases=aliases,
            taxonomy_mappings=mappings,
            observations=observations,
            related_ads=[],
        )

    def graph(self, conn: sqlite3.Connection, *, limit: int = 400) -> GraphPayload:
        nodes = [
            rows.node(row)
            for row in conn.execute(
                "SELECT * FROM entity_nodes WHERE status <> 'rejected' ORDER BY type, canonical_name LIMIT ?",
                (limit,),
            ).fetchall()
        ]
        node_ids = {node.id for node in nodes}
        edges = [
            rows.edge(row)
            for row in conn.execute(
                "SELECT * FROM entity_edges WHERE status <> 'rejected' ORDER BY relation LIMIT ?",
                (limit * 2,),
            ).fetchall()
            if row["source_node_id"] in node_ids and row["target_node_id"] in node_ids
        ]
        return GraphPayload(nodes=nodes, edges=edges)

    def list_taxonomy_mappings(
        self, conn: sqlite3.Connection, *, limit: int = 200
    ) -> list[TaxonomyMappingSummary]:
        result_rows = conn.execute(
            """
            SELECT tm.*, n.id AS n_id, n.type AS n_type, n.canonical_name AS n_name,
                   n.normalized_name AS n_norm, n.description AS n_desc, n.status AS n_status,
                   n.confidence AS n_confidence, n.generated_from_json AS n_generated,
                   n.created_at AS n_created_at, n.updated_at AS n_updated_at
            FROM taxonomy_mappings tm
            JOIN entity_nodes n ON n.id = tm.entity_id
            ORDER BY tm.confidence DESC, n.canonical_name
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            TaxonomyMappingSummary(mapping=rows.mapping(row), entity=rows.joined_node(row))
            for row in result_rows
        ]

    def record_resolver_run(
        self,
        conn: sqlite3.Connection,
        *,
        run_id: str,
        mode: str,
        fully_automatic: bool,
        source_ad_count: int,
        created_count: int,
        candidate_count: int,
        confirmed_unreviewed_count: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO resolver_runs (
              id, mode, fully_automatic, source_ad_count, created_count,
              candidate_count, confirmed_unreviewed_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                mode,
                int(fully_automatic),
                source_ad_count,
                created_count,
                candidate_count,
                confirmed_unreviewed_count,
            ),
        )

    def _product_summary(self, conn: sqlite3.Connection, node: EntityNode) -> ProductSummary:
        brand = _first_related(conn, node.id, "BRANDED_BY")
        owner = _first_related(conn, brand.id, "OWNED_BY") if brand else None
        category = _first_related(conn, node.id, "IN_CATEGORY")
        counts = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM entity_aliases WHERE node_id = ?) AS aliases_count,
              (SELECT COUNT(DISTINCT normalized_alias) FROM entity_aliases WHERE node_id = ?) AS distinct_aliases_count,
              (SELECT COUNT(*) FROM entity_observations WHERE node_id = ?) AS evidence_count,
              (SELECT COUNT(DISTINCT ad_id) FROM entity_observations WHERE node_id = ?) AS ads_count,
              (SELECT COUNT(*) FROM taxonomy_mappings WHERE entity_id = ?) AS mapping_count
            """,
            (node.id, node.id, node.id, node.id, node.id),
        ).fetchone()
        return ProductSummary(
            node=node,
            brand=brand,
            owner=owner,
            category=category,
            aliases_count=int(counts["distinct_aliases_count"] or counts["aliases_count"] or 0),
            evidence_count=int(counts["evidence_count"] or 0),
            related_ads_count=int(counts["ads_count"] or 0),
            taxonomy_mappings_count=int(counts["mapping_count"] or 0),
        )


def _dedupe_aliases(aliases: list[EntityAlias]) -> list[EntityAlias]:
    by_key: dict[str, EntityAlias] = {}
    for alias in aliases:
        current = by_key.get(alias.normalized_alias)
        if current is None or (alias.confidence, alias.status) > (
            current.confidence,
            current.status,
        ):
            by_key[alias.normalized_alias] = alias
    return sorted(by_key.values(), key=lambda item: item.alias.lower())


def _first_related(conn: sqlite3.Connection, source_id: str, relation: str) -> EntityNode | None:
    row = conn.execute(
        """
        SELECT n.*
        FROM entity_edges e
        JOIN entity_nodes n ON n.id = e.target_node_id
        WHERE e.source_node_id = ? AND e.relation = ? AND n.status <> 'rejected'
        ORDER BY e.confidence DESC, n.canonical_name
        LIMIT 1
        """,
        (source_id, relation),
    ).fetchone()
    return rows.node(row) if row else None


def _dedupe_product_summaries(
    summaries: list[ProductSummary], crawler_config: EntityCrawlerConfig
) -> list[ProductSummary]:
    grouped: dict[str, ProductSummary] = {}
    grouped_scores: dict[str, tuple[int, int, int, int, int]] = {}
    for summary in summaries:
        key = product_resolution_key(summary.node.canonical_name, crawler_config)
        if not key:
            continue
        score = _product_summary_score(summary, key)
        current = grouped_scores.get(key)
        if current is None or score > current:
            grouped[key] = summary
            grouped_scores[key] = score
    return sorted(
        grouped.values(),
        key=lambda item: (item.node.status, item.node.canonical_name.lower()),
        reverse=True,
    )


def _product_summary_score(summary: ProductSummary, family_key: str) -> tuple[int, int, int, int, int]:
    exact_name = int(normalize_name(summary.node.canonical_name) == family_key)
    return (
        exact_name,
        summary.related_ads_count,
        summary.evidence_count,
        summary.aliases_count,
        -len(summary.node.canonical_name),
    )
