from __future__ import annotations

import sqlite3

from ad_classifier.db.repositories.base import db_value, row_to_dict
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

    def get(self, ad_id: str) -> AdRecord | None:
        row = self.conn.execute("SELECT * FROM ads WHERE id = ?", (ad_id,)).fetchone()
        data = row_to_dict(row)
        return AdRecord.model_validate(data) if data is not None else None

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
