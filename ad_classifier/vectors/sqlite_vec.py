from __future__ import annotations

import sqlite3

from ad_classifier.vectors.store import deserialize_float32, serialize_float32


class SqliteVecStore:
    """sqlite-vec backed vector store for text and visual ad embeddings."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        text_dim: int = 384,
        visual_dim: int = 768,
    ) -> None:
        self.conn = conn
        self.text_dim = text_dim
        self.visual_dim = visual_dim

    def ensure_tables(self) -> None:
        self.conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_ads_text USING vec0(
                ad_id TEXT PRIMARY KEY,
                embedding FLOAT[{self.text_dim}]
            )
            """
        )
        self.conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_ads_visual USING vec0(
                ad_id TEXT PRIMARY KEY,
                embedding FLOAT[{self.visual_dim}]
            )
            """
        )

    # ------------------------------------------------------------------
    # Text embeddings
    # ------------------------------------------------------------------

    def upsert_text(self, ad_id: str, vector: list[float]) -> None:
        blob = serialize_float32(vector)
        # vec0 does not support INSERT OR REPLACE; delete-then-insert instead
        self.conn.execute("DELETE FROM vec_ads_text WHERE ad_id = ?", (ad_id,))
        self.conn.execute(
            "INSERT INTO vec_ads_text(ad_id, embedding) VALUES (?, ?)",
            (ad_id, blob),
        )

    def get_text(self, ad_id: str) -> list[float] | None:
        row = self.conn.execute(
            "SELECT embedding FROM vec_ads_text WHERE ad_id = ?", (ad_id,)
        ).fetchone()
        return deserialize_float32(row[0]) if row else None

    def search_text(self, query: list[float], k: int = 10) -> list[tuple[str, float]]:
        blob = serialize_float32(query)
        rows = self.conn.execute(
            """
            SELECT ad_id, distance
            FROM vec_ads_text
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
            """,
            (blob, k),
        ).fetchall()
        return [(row[0], float(row[1])) for row in rows]

    # ------------------------------------------------------------------
    # Visual embeddings
    # ------------------------------------------------------------------

    def upsert_visual(self, ad_id: str, vector: list[float]) -> None:
        blob = serialize_float32(vector)
        self.conn.execute("DELETE FROM vec_ads_visual WHERE ad_id = ?", (ad_id,))
        self.conn.execute(
            "INSERT INTO vec_ads_visual(ad_id, embedding) VALUES (?, ?)",
            (ad_id, blob),
        )

    def get_visual(self, ad_id: str) -> list[float] | None:
        row = self.conn.execute(
            "SELECT embedding FROM vec_ads_visual WHERE ad_id = ?", (ad_id,)
        ).fetchone()
        return deserialize_float32(row[0]) if row else None

    def search_visual(self, query: list[float], k: int = 10) -> list[tuple[str, float]]:
        blob = serialize_float32(query)
        rows = self.conn.execute(
            """
            SELECT ad_id, distance
            FROM vec_ads_visual
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
            """,
            (blob, k),
        ).fetchall()
        return [(row[0], float(row[1])) for row in rows]

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, ad_id: str) -> None:
        self.conn.execute("DELETE FROM vec_ads_text WHERE ad_id = ?", (ad_id,))
        self.conn.execute("DELETE FROM vec_ads_visual WHERE ad_id = ?", (ad_id,))
