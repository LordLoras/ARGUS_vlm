from __future__ import annotations

import re
from typing import Any


def group_frame_hits(
    frame_hits: list[dict[str, Any]],
    *,
    source: str,
    exclude_ad_id: str | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for hit in frame_hits:
        ad_id = str(hit["ad_id"])
        if ad_id == exclude_ad_id:
            continue
        item = grouped.setdefault(
            ad_id,
            {
                "ad_id": ad_id,
                "distance": hit["distance"],
                "source": source,
                "matched_frames": [],
            },
        )
        item["distance"] = min(float(item["distance"]), float(hit["distance"]))
        if len(item["matched_frames"]) < 3:
            item["matched_frames"].append(
                {
                    "frame_index": hit["frame_index"],
                    "time_ms": hit["time_ms"],
                    "path": hit["path"],
                    "distance": hit["distance"],
                }
            )
    return sorted(grouped.values(), key=lambda row: float(row.get("distance", 999.0)))


def filter_hits(
    conn,
    hits: list[dict[str, Any]],
    *,
    brand: str | None,
    category: str | None,
    status: str | None,
    k: int,
) -> list[dict[str, Any]]:
    if not hits:
        return []
    if not any((brand, category, status)):
        return hits[:k]

    ad_ids = [hit["ad_id"] for hit in hits]
    placeholders = ", ".join("?" for _ in ad_ids)
    clauses = [f"id IN ({placeholders})"]
    params: list[Any] = list(ad_ids)
    if brand:
        clauses.append("(brand_name LIKE ? OR advertiser_name LIKE ?)")
        params.extend([f"%{brand}%", f"%{brand}%"])
    if category:
        clauses.append("primary_category = ?")
        params.append(category)
    if status:
        clauses.append("status = ?")
        params.append(status)

    rows = conn.execute(
        f"SELECT id FROM ads WHERE {' AND '.join(clauses)}",
        params,
    ).fetchall()
    allowed = {row["id"] for row in rows}
    return [hit for hit in hits if hit["ad_id"] in allowed][:k]


def rerank_hits(conn, hits: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    if not hits:
        return []
    tokens = {
        token.casefold()
        for token in re.findall(r"[a-z0-9]+", query)
        if len(token) >= 3
    }
    if not tokens:
        return hits

    ad_text = _ad_text_by_id(conn, [hit["ad_id"] for hit in hits])
    frame_text = _frame_text_by_key(conn, hits)

    reranked: list[dict[str, Any]] = []
    for hit in hits:
        base = 1.0 / (1.0 + float(hit.get("distance", hit.get("vec_distance", 1.0)) or 1.0))
        haystack = ad_text.get(hit["ad_id"], "")
        for frame in hit.get("matched_frames", []):
            haystack += " " + frame_text.get((hit["ad_id"], int(frame["frame_index"])), "")
        haystack_tokens = set(re.findall(r"[a-z0-9]+", haystack))
        matched = sorted(
            token for token in tokens if _token_matches_evidence(token, haystack_tokens)
        )
        score = base + min(len(matched), 4) * 0.05
        next_hit = dict(hit)
        next_hit["rerank_score"] = score
        if matched:
            next_hit["rerank_reason"] = f"matched text evidence: {', '.join(matched[:4])}"
        else:
            next_hit["rerank_reason"] = "visual similarity"
        reranked.append(next_hit)
    return sorted(reranked, key=lambda row: float(row.get("rerank_score", 0.0)), reverse=True)


def _ad_text_by_id(conn, ad_ids: list[str]) -> dict[str, str]:
    placeholders = ", ".join("?" for _ in ad_ids)
    rows = conn.execute(
        f"""
        SELECT id, brand_name, advertiser_name, products_text, primary_category
        FROM ads
        WHERE id IN ({placeholders})
        """,
        ad_ids,
    ).fetchall()
    return {
        row["id"]: " ".join(
            str(row[key] or "")
            for key in ("brand_name", "advertiser_name", "products_text", "primary_category")
        ).casefold()
        for row in rows
    }


def _frame_text_by_key(conn, hits: list[dict[str, Any]]) -> dict[tuple[str, int], str]:
    frame_pairs = [
        (hit["ad_id"], frame["frame_index"])
        for hit in hits
        for frame in hit.get("matched_frames", [])
    ]
    if not frame_pairs:
        return {}

    clauses = " OR ".join("(f.ad_id = ? AND f.frame_index = ?)" for _ in frame_pairs)
    params: list[Any] = []
    for ad_id, frame_index in frame_pairs:
        params.extend([ad_id, frame_index])
    rows = conn.execute(
        f"""
        SELECT f.ad_id, f.frame_index, group_concat(o.text, ' ') AS text
        FROM frames f
        JOIN ocr_items o ON o.frame_id = f.id
        WHERE {clauses}
        GROUP BY f.ad_id, f.frame_index
        """,
        params,
    ).fetchall()
    return {
        (row["ad_id"], int(row["frame_index"])): (row["text"] or "").casefold()
        for row in rows
    }


def _token_matches_evidence(token: str, haystack_tokens: set[str]) -> bool:
    if token in haystack_tokens:
        return True
    if token == "gov":
        return any(candidate.startswith("govern") for candidate in haystack_tokens)
    if len(token) >= 4:
        return any(candidate.startswith(token) for candidate in haystack_tokens)
    return False
