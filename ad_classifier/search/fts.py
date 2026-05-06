from __future__ import annotations

import sqlite3


def fts_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
) -> list[tuple[str, float]]:
    """Query the ads_fts FTS5 table.

    Returns list of (ad_id, rank) sorted by relevance (rank is negative from FTS5,
    we return the absolute value so higher = more relevant).
    """
    rows = conn.execute(
        """
        SELECT ad_id, rank
        FROM ads_fts
        WHERE ads_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()
    # FTS5 rank is negative — negate so higher value means better match
    return [(row[0], abs(float(row[1]))) for row in rows]


def fts_update(
    conn: sqlite3.Connection,
    ad_id: str,
    *,
    brand: str = "",
    products: str = "",
    primary_category: str = "",
    transcript_text: str = "",
    ocr_text: str = "",
    marketing_entities_text: str = "",
) -> None:
    """Insert or replace a row in ads_fts."""
    conn.execute("DELETE FROM ads_fts WHERE ad_id = ?", (ad_id,))
    conn.execute(
        """
        INSERT INTO ads_fts
          (ad_id, brand, products, primary_category, transcript_text, ocr_text, marketing_entities_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ad_id, brand, products, primary_category, transcript_text, ocr_text, marketing_entities_text),
    )


def fts_delete(conn: sqlite3.Connection, ad_id: str) -> None:
    conn.execute("DELETE FROM ads_fts WHERE ad_id = ?", (ad_id,))
