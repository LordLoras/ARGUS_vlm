"""Authoritative latest-resource projection persistence and reads."""

from __future__ import annotations

import sqlite3

from ad_classifier.entity_graph.rows import loads_dict, to_json
from ad_classifier.intelligence_crawler.models import (
    IntelResource,
    IntelResourceArtifact,
    IntelResourceView,
)
from ad_classifier.intelligence_crawler.repository_rows import resource_filters, resource_view
from ad_classifier.intelligence_crawler.timeutils import iso


class ResourceRepositoryMixin:
    def existing_resource_ids(self, conn: sqlite3.Connection, source_id: str) -> set[str]:
        rows = conn.execute(
            "SELECT id FROM intel_resources WHERE source_id = ?", (source_id,)
        ).fetchall()
        return {str(row["id"]) for row in rows}

    def insert_resource(self, conn: sqlite3.Connection, resource: IntelResource) -> bool:
        existed = (
            conn.execute("SELECT 1 FROM intel_resources WHERE id = ?", (resource.id,)).fetchone()
            is not None
        )
        cur = conn.execute(
            """
            INSERT INTO intel_resources
              (id, source_id, run_id, resource_type, url, canonical_url, platform, platform_id,
               content_hash, title, description, published_at, first_seen_at, fetched_at,
               last_seen_at, is_backfill, variant_count, has_variants, thumbnail_url,
               duration_ms, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              run_id=excluded.run_id, resource_type=excluded.resource_type,
              url=excluded.url, canonical_url=excluded.canonical_url,
              platform=excluded.platform, platform_id=excluded.platform_id,
              content_hash=excluded.content_hash, title=excluded.title,
              description=excluded.description, published_at=excluded.published_at,
              last_seen_at=excluded.last_seen_at, fetched_at=excluded.fetched_at,
              variant_count=excluded.variant_count, has_variants=excluded.has_variants,
              thumbnail_url=excluded.thumbnail_url, duration_ms=excluded.duration_ms,
              metadata_json=excluded.metadata_json
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
                iso(resource.last_seen_at or resource.fetched_at),
                int(resource.is_backfill),
                resource.variant_count,
                int(resource.has_variants),
                resource.thumbnail_url,
                resource.duration_ms,
                to_json(resource.metadata),
            ),
        )
        return cur.rowcount > 0 and not existed

    def get_resource_metadata(self, conn: sqlite3.Connection, resource_id: str) -> dict | None:
        row = conn.execute(
            "SELECT metadata_json FROM intel_resources WHERE id = ?", (resource_id,)
        ).fetchone()
        return (loads_dict(row["metadata_json"]) or {}) if row is not None else None

    def get_resource(self, conn: sqlite3.Connection, resource_id: str) -> IntelResourceView | None:
        row = conn.execute(
            "SELECT r.*, s.brand_name, s.source_type FROM intel_resources r "
            "JOIN intel_sources s ON s.id = r.source_id WHERE r.id = ?",
            (resource_id,),
        ).fetchone()
        if row is None:
            return None
        media = self._media_assets_for(conn, [resource_id]).get(resource_id, [])
        return resource_view(row, media)

    def count_resources(
        self,
        conn: sqlite3.Connection,
        *,
        brand: str | None = None,
        source_id: str | None = None,
        include_backfill: bool = True,
    ) -> int:
        clauses, params = resource_filters(
            brand=brand, source_id=source_id, include_backfill=include_backfill
        )
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM intel_resources r "
            f"JOIN intel_sources s ON s.id = r.source_id {where}",
            params,
        ).fetchone()
        return int(row["n"] or 0)

    def list_resources(
        self,
        conn: sqlite3.Connection,
        *,
        brand: str | None = None,
        source_id: str | None = None,
        include_backfill: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IntelResourceView]:
        clauses, params = resource_filters(
            brand=brand, source_id=source_id, include_backfill=include_backfill
        )
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        rows = conn.execute(
            f"""
            SELECT r.*, s.brand_name, s.source_type
            FROM intel_resources r JOIN intel_sources s ON s.id = r.source_id
            {where}
            ORDER BY COALESCE(r.published_at, r.first_seen_at) DESC, r.first_seen_at DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        media = self._media_assets_for(conn, [str(row["id"]) for row in rows])
        return [resource_view(row, media.get(str(row["id"]), [])) for row in rows]

    def _media_assets_for(
        self, conn: sqlite3.Connection, resource_ids: list[str]
    ) -> dict[str, list[IntelResourceArtifact]]:
        if not resource_ids:
            return {}
        placeholders = ",".join("?" * len(resource_ids))
        rows = conn.execute(
            f"SELECT resource_id, asset_type, url, thumbnail_url FROM intel_media_assets "
            f"WHERE resource_id IN ({placeholders}) ORDER BY asset_type, url",
            resource_ids,
        ).fetchall()
        artifacts: dict[str, list[IntelResourceArtifact]] = {}
        for row in rows:
            resource_id = str(row["resource_id"])
            artifacts.setdefault(resource_id, []).append(
                IntelResourceArtifact(
                    artifact_type=f"media_asset:{row['asset_type']}",
                    label=str(row["asset_type"]),
                    url=row["url"] or row["thumbnail_url"],
                )
            )
        return artifacts
