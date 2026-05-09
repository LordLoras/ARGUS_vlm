from __future__ import annotations

import sqlite3
from pathlib import Path

from ad_classifier.db.repositories.base import db_value, row_to_dict
from ad_classifier.dedup.phash import hamming_distance
from ad_classifier.models.ads import AdRecord
from ad_classifier.search.query_expansion import (
    build_loose_like_clause,
    has_alias_expansion,
)


class AdRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, ad: AdRecord) -> None:
        data = ad.model_dump()
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        values = [db_value(value) for value in data.values()]
        self.conn.execute(
            f"INSERT INTO ads ({columns}) VALUES ({placeholders})",
            values,
        )

    def upsert_ingest(self, ad: AdRecord) -> None:
        data = ad.model_dump()
        columns = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        update_columns = [
            "source_path",
            "duration_ms",
            "width",
            "height",
            "fps",
            "status",
            "source_hash",
            "phash_mean",
        ]
        assignments = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
        values = [db_value(value) for value in data.values()]
        self.conn.execute(
            f"""
            INSERT INTO ads ({columns}) VALUES ({placeholders})
            ON CONFLICT(id) DO UPDATE SET {assignments}
            """,
            values,
        )

    def get(self, ad_id: str) -> AdRecord | None:
        row = self.conn.execute("SELECT * FROM ads WHERE id = ?", (ad_id,)).fetchone()
        data = row_to_dict(row)
        return AdRecord.model_validate(data) if data is not None else None

    def list(
        self,
        *,
        brand: str | None = None,
        category: str | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AdRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if brand:
            clauses.append("brand_name = ?")
            params.append(brand)
        if category:
            if has_alias_expansion(category):
                loose_clause, loose_params = build_loose_like_clause(category)
                clauses.append(f"(primary_category = ? OR {loose_clause})")
                params.append(category)
                params.extend(loose_params)
            else:
                clauses.append("primary_category = ?")
                params.append(category)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if q:
            loose_clause, loose_params = build_loose_like_clause(q)
            if loose_clause:
                clauses.append(loose_clause)
                params.extend(loose_params)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT *
            FROM ads
            {where}
            ORDER BY ingested_at DESC, id
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
        return [AdRecord.model_validate(row_to_dict(row)) for row in rows]

    def update_status(self, ad_id: str, status: str) -> None:
        self.conn.execute("UPDATE ads SET status = ? WHERE id = ?", (status, ad_id))

    def update_source_path(self, ad_id: str, source_path: Path | str) -> None:
        self.conn.execute(
            "UPDATE ads SET source_path = ? WHERE id = ?",
            (str(source_path), ad_id),
        )

    def find_by_source_hash(
        self,
        source_hash: str,
        *,
        exclude_ad_id: str | None = None,
    ) -> AdRecord | None:
        if exclude_ad_id is None:
            row = self.conn.execute(
                "SELECT * FROM ads WHERE source_hash = ? ORDER BY ingested_at LIMIT 1",
                (source_hash,),
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT *
                FROM ads
                WHERE source_hash = ?
                  AND id <> ?
                ORDER BY ingested_at
                LIMIT 1
                """,
                (source_hash, exclude_ad_id),
            ).fetchone()
        data = row_to_dict(row)
        return AdRecord.model_validate(data) if data is not None else None

    def find_nearest_phash(
        self,
        phash_mean: str,
        *,
        exclude_ad_id: str | None = None,
    ) -> tuple[AdRecord, int] | None:
        if exclude_ad_id is None:
            rows = self.conn.execute(
                "SELECT * FROM ads WHERE phash_mean IS NOT NULL",
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM ads WHERE phash_mean IS NOT NULL AND id <> ?",
                (exclude_ad_id,),
            ).fetchall()

        nearest: tuple[AdRecord, int] | None = None
        for row in rows:
            data = row_to_dict(row)
            if data is None:
                continue
            ad = AdRecord.model_validate(data)
            if ad.phash_mean is None:
                continue
            distance = hamming_distance(phash_mean, ad.phash_mean)
            if nearest is None or distance < nearest[1]:
                nearest = (ad, distance)
        return nearest

    def update_projection(
        self,
        ad_id: str,
        *,
        brand_name: str | None,
        brand_confidence: float | None,
        advertiser_name: str | None = None,
        website_domain: str | None = None,
        phone_number: str | None = None,
        landing_page_domain: str | None = None,
        products_text: str | None,
        primary_category: str | None,
        subcategory: str | None = None,
        decision: str | None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE ads
            SET brand_name = ?,
                brand_confidence = ?,
                advertiser_name = ?,
                website_domain = ?,
                phone_number = ?,
                landing_page_domain = ?,
                products_text = ?,
                primary_category = ?,
                subcategory = ?,
                decision = ?
            WHERE id = ?
            """,
            (
                brand_name,
                brand_confidence,
                advertiser_name,
                website_domain,
                phone_number,
                landing_page_domain,
                products_text,
                primary_category,
                subcategory,
                decision,
                ad_id,
            ),
        )

    def delete(self, ad_id: str) -> None:
        self.conn.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
