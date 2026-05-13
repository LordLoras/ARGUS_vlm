from __future__ import annotations

import sqlite3

from ad_classifier.vectors.store import deserialize_float32, serialize_float32


class SqliteVecStore:
    """sqlite-vec backed vector store for text, ad visual, and frame visual embeddings."""

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
        self.conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS vec_frames_visual USING vec0(
                frame_key TEXT PRIMARY KEY,
                embedding FLOAT[{self.visual_dim}]
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visual_frame_vectors (
                frame_key TEXT PRIMARY KEY,
                ad_id TEXT NOT NULL,
                frame_index INTEGER NOT NULL,
                time_ms INTEGER NOT NULL,
                FOREIGN KEY(ad_id) REFERENCES ads(id) ON DELETE CASCADE,
                UNIQUE(ad_id, frame_index)
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_visual_frame_vectors_ad
            ON visual_frame_vectors(ad_id)
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
    # Per-frame visual embeddings
    # ------------------------------------------------------------------

    def upsert_frame_visual(
        self,
        ad_id: str,
        frame_index: int,
        time_ms: int,
        vector: list[float],
    ) -> None:
        frame_key = self.frame_key(ad_id, frame_index)
        blob = serialize_float32(vector)
        self.conn.execute("DELETE FROM vec_frames_visual WHERE frame_key = ?", (frame_key,))
        self.conn.execute(
            "INSERT INTO vec_frames_visual(frame_key, embedding) VALUES (?, ?)",
            (frame_key, blob),
        )
        self.conn.execute(
            """
            INSERT OR REPLACE INTO visual_frame_vectors
              (frame_key, ad_id, frame_index, time_ms)
            VALUES (?, ?, ?, ?)
            """,
            (frame_key, ad_id, frame_index, time_ms),
        )

    def delete_frame_visuals(self, ad_id: str) -> None:
        rows = self.conn.execute(
            "SELECT frame_key FROM visual_frame_vectors WHERE ad_id = ?", (ad_id,)
        ).fetchall()
        for row in rows:
            self.conn.execute(
                "DELETE FROM vec_frames_visual WHERE frame_key = ?", (row["frame_key"],)
            )
        self.conn.execute("DELETE FROM visual_frame_vectors WHERE ad_id = ?", (ad_id,))

    def search_frame_visual(
        self,
        query: list[float],
        k: int = 50,
    ) -> list[dict[str, float | int | str]]:
        blob = serialize_float32(query)
        rows = self.conn.execute(
            """
            SELECT frame_key, distance
            FROM vec_frames_visual
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
            """,
            (blob, k),
        ).fetchall()
        if not rows:
            return []

        frame_keys = [row["frame_key"] for row in rows]
        placeholders = ", ".join("?" for _ in frame_keys)
        metadata_rows = self.conn.execute(
            f"""
            SELECT v.frame_key, v.ad_id, v.frame_index, v.time_ms, f.path
            FROM visual_frame_vectors v
            LEFT JOIN frames f
              ON f.ad_id = v.ad_id AND f.frame_index = v.frame_index
            WHERE v.frame_key IN ({placeholders})
            """,
            frame_keys,
        ).fetchall()
        metadata = {row["frame_key"]: dict(row) for row in metadata_rows}

        out: list[dict[str, float | int | str]] = []
        for row in rows:
            item = metadata.get(row["frame_key"])
            if not item:
                continue
            out.append(
                {
                    "frame_key": row["frame_key"],
                    "ad_id": item["ad_id"],
                    "frame_index": int(item["frame_index"]),
                    "time_ms": int(item["time_ms"]),
                    "path": item["path"] or "",
                    "distance": float(row["distance"]),
                }
            )
        return out

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, ad_id: str) -> None:
        self.conn.execute("DELETE FROM vec_ads_text WHERE ad_id = ?", (ad_id,))
        self.conn.execute("DELETE FROM vec_ads_visual WHERE ad_id = ?", (ad_id,))
        self.delete_frame_visuals(ad_id)

    @staticmethod
    def frame_key(ad_id: str, frame_index: int) -> str:
        return f"{ad_id}:{frame_index}"
