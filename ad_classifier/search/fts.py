from __future__ import annotations

import sqlite3

from ad_classifier.search.query_expansion import (
    build_loose_like_clause,
    expand_query_terms,
    has_alias_expansion,
)


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


def fts_search_expanded(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 20,
) -> list[tuple[str, float]]:
    """Search FTS with business-topic aliases while preserving first-hit order."""
    if not query.strip():
        return []

    if has_alias_expansion(query):
        clause, params = build_loose_like_clause(query)
        if not clause:
            return []
        rows = conn.execute(
            f"""
            SELECT id
            FROM ads
            WHERE {clause}
            ORDER BY ingested_at DESC, id
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        return [(row[0], 1.0) for row in rows]

    terms = expand_query_terms(query)
    seen: dict[str, tuple[float, int]] = {}
    order = 0
    for term in terms:
        try:
            rows = fts_search(conn, _quote_fts5(term), limit=limit)
        except Exception:
            continue
        for ad_id, score in rows:
            if ad_id not in seen:
                seen[ad_id] = (score, order)
                order += 1
            else:
                best_score, first_order = seen[ad_id]
                seen[ad_id] = (max(best_score, score), first_order)

    ranked = sorted(seen.items(), key=lambda item: item[1][1])
    return [(ad_id, score) for ad_id, (score, _order) in ranked[:limit]]


def _quote_fts5(term: str) -> str:
    escaped = term.replace('"', '""')
    return f'"{escaped}"'


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
