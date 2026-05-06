from __future__ import annotations

import sqlite3

from ad_classifier.db.repositories.base import db_value, row_to_dict
from ad_classifier.dedup.phash import hamming_distance
from ad_classifier.models.ads import AdRecord


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
        products_text: str | None,
        primary_category: str | None,
        decision: str | None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE ads
            SET brand_name = ?,
                brand_confidence = ?,
                products_text = ?,
                primary_category = ?,
                decision = ?
            WHERE id = ?
            """,
            (
                brand_name,
                brand_confidence,
                products_text,
                primary_category,
                decision,
                ad_id,
            ),
        )
