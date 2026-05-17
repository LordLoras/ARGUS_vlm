from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from ad_classifier.api.deps import open_request_db

router = APIRouter(tags=["stats"])


@router.get("/stats")
def get_stats(
    request: Request,
    brand: str | None = None,
    category: str | None = None,
    status: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        where, params = _filters(brand=brand, category=category, status=status)
        total = conn.execute(f"SELECT COUNT(*) FROM ads {where}", params).fetchone()[0]
        return {
            "total_ads": int(total),
            "by_status": _counts(conn, "status", where, params, limit),
            "by_category": _counts(conn, "primary_category", where, params, limit),
            "by_brand": _counts(conn, "brand_name", where, params, limit),
            "risk_labels": _risk_counts(conn, where, params, limit),
        }
    finally:
        conn.close()


def _filters(
    *,
    brand: str | None,
    category: str | None,
    status: str | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if brand:
        clauses.append("LOWER(brand_name) = LOWER(?)")
        params.append(brand)
    if category:
        clauses.append("primary_category = ?")
        params.append(category)
    if status:
        clauses.append("status = ?")
        params.append(status)
    return (f"WHERE {' AND '.join(clauses)}" if clauses else "", params)


def _counts(conn, column: str, where: str, params: list[Any], limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT {column} AS value, COUNT(*) AS count
        FROM ads
        {where}
        GROUP BY {column}
        ORDER BY count DESC, value IS NULL, value
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [{"value": row["value"], "count": int(row["count"])} for row in rows]


def _risk_counts(conn, where: str, params: list[Any], limit: int) -> list[dict[str, Any]]:
    join_where = where.replace("WHERE", "AND", 1) if where else ""
    rows = conn.execute(
        f"""
        SELECT json_each.value AS value, COUNT(*) AS count
        FROM classifications c
        JOIN ads ON ads.id = c.ad_id
        JOIN json_each(
          CASE
            WHEN json_valid(c.risk_labels_json) THEN c.risk_labels_json
            ELSE '[]'
          END
        )
        WHERE 1 = 1
        {join_where}
        GROUP BY json_each.value
        ORDER BY count DESC, value
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [{"value": row["value"], "count": int(row["count"])} for row in rows]
