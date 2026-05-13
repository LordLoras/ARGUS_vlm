from __future__ import annotations

import math
import re
from typing import Any

from ad_classifier.vectors.sqlite_vec import SqliteVecStore

_INTENT_CATEGORY_TERMS: dict[str, set[str]] = {
    "automotive": {
        "auto",
        "automotive",
        "car",
        "cars",
        "suv",
        "suvs",
        "truck",
        "trucks",
        "vehicle",
        "vehicles",
        "wrangler",
        "cherokee",
        "gladiator",
    },
    "healthcare_pharma": {
        "cardiologist",
        "cholesterol",
        "doctor",
        "health",
        "medical",
        "supplement",
    },
    "legal": {"attorney", "attorneys", "injury", "law", "lawyer", "legal"},
    "entertainment_media": {"hockey", "show", "tv", "weekly"},
    "political": {"candidate", "campaign", "governor", "political"},
}


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


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


def filter_by_query_intent(
    conn, hits: list[dict[str, Any]], query: str | None
) -> list[dict[str, Any]]:
    if not hits or not query:
        return hits
    tokens = set(re.findall(r"[a-z0-9]+", query.casefold()))
    categories = {
        category
        for category, category_tokens in _INTENT_CATEGORY_TERMS.items()
        if tokens & category_tokens
    }
    if not categories:
        return hits

    ad_ids = [hit["ad_id"] for hit in hits]
    id_placeholders = ", ".join("?" for _ in ad_ids)
    category_placeholders = ", ".join("?" for _ in categories)
    rows = conn.execute(
        f"""
        SELECT id
        FROM ads
        WHERE id IN ({id_placeholders})
          AND primary_category IN ({category_placeholders})
        """,
        [*ad_ids, *categories],
    ).fetchall()
    allowed = {row["id"] for row in rows}
    return [hit for hit in hits if hit["ad_id"] in allowed]


def rerank_hits(conn, hits: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    if not hits:
        return []
    tokens = {token.casefold() for token in re.findall(r"[a-z0-9]+", query) if len(token) >= 3}
    if not tokens:
        return hits

    ad_text = _ad_text_by_id(conn, [hit["ad_id"] for hit in hits])
    frame_text = _frame_text_by_key(conn, hits)

    reranked: list[dict[str, Any]] = []
    for hit in hits:
        distance = hit.get("distance")
        if distance is None:
            distance = hit.get("vec_distance")
        if distance is not None:
            base = 1.0 / (1.0 + float(distance))
        elif hit.get("score") is not None:
            base = float(hit["score"])
        elif hit.get("rrf_score") is not None:
            base = min(float(hit["rrf_score"]) * 20.0, 1.0)
        else:
            base = 0.5
        haystack = ad_text.get(hit["ad_id"], "")
        for frame in hit.get("matched_frames", []):
            haystack += " " + frame_text.get((hit["ad_id"], int(frame["frame_index"])), "")
        haystack_tokens = set(re.findall(r"[a-z0-9]+", haystack))
        matched = sorted(
            token for token in tokens if _token_matches_evidence(token, haystack_tokens)
        )
        match_ratio = len(matched) / len(tokens)
        if matched:
            score = base * (1.0 + match_ratio) + len(matched) * 0.05
            next_hit = dict(hit)
            next_hit["rerank_score"] = round(score, 6)
            next_hit["rerank_reason"] = f"matched text evidence: {', '.join(matched[:4])}"
        else:
            score = base * 0.6
            next_hit = dict(hit)
            next_hit["rerank_score"] = round(score, 6)
            next_hit["rerank_reason"] = "visual similarity"
        reranked.append(next_hit)
    return sorted(reranked, key=lambda row: float(row.get("rerank_score", 0.0)), reverse=True)


def _ad_text_by_id(conn, ad_ids: list[str]) -> dict[str, str]:
    placeholders = ", ".join("?" for _ in ad_ids)
    rows = conn.execute(
        f"""
        SELECT
          a.id,
          a.brand_name,
          a.advertiser_name,
          a.products_text,
          a.primary_category,
          a.subcategory,
          a.website_domain,
          a.phone_number,
          a.landing_page_domain,
          ft.transcript_text AS fts_transcript_text,
          ft.ocr_text AS fts_ocr_text,
          ft.marketing_entities_text AS fts_marketing_entities_text,
          (
            SELECT group_concat(t.text, ' ')
            FROM transcript_segments t
            WHERE t.ad_id = a.id
          ) AS transcript_text,
          (
            SELECT group_concat(o.text, ' ')
            FROM frames f
            JOIN ocr_items o ON o.frame_id = f.id
            WHERE f.ad_id = a.id
          ) AS ocr_text
        FROM ads a
        LEFT JOIN ads_fts ft ON ft.ad_id = a.id
        WHERE a.id IN ({placeholders})
        """,
        ad_ids,
    ).fetchall()
    return {
        row["id"]: " ".join(
            str(row[key] or "")
            for key in (
                "brand_name",
                "advertiser_name",
                "products_text",
                "primary_category",
                "subcategory",
                "website_domain",
                "phone_number",
                "landing_page_domain",
                "fts_transcript_text",
                "fts_ocr_text",
                "fts_marketing_entities_text",
                "transcript_text",
                "ocr_text",
            )
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
    return {(row["ad_id"], int(row["frame_index"])): (row["text"] or "").casefold() for row in rows}


def _token_matches_evidence(token: str, haystack_tokens: set[str]) -> bool:
    if token in haystack_tokens:
        return True
    if token == "gov":
        return any(candidate.startswith("govern") for candidate in haystack_tokens)
    if len(token) >= 4:
        return any(candidate.startswith(token) for candidate in haystack_tokens)
    return False


def filter_by_min_score(
    store: SqliteVecStore,
    hits: list[dict[str, Any]],
    query_vector: list[float],
    *,
    min_score: float,
    modality: str,
) -> list[dict[str, Any]]:
    """Remove hits below a cosine-similarity threshold.

    For visual modality, computes the max similarity across each hit's
    best-matching frame vectors AND the ad-level vector — if ANY keyframe
    clears the bar, the ad survives (ad-level vectors are mean-pooled from
    all keyframes, which dilutes the signal; per-frame checking recovers it).

    The surviving hits get a ``score`` field (rounded to 4 decimal places).

    Returns the filtered list (preserving original order).
    """
    if min_score <= 0 or not hits:
        return hits

    ad_getter = store.get_visual if modality == "visual" else store.get_text

    frame_keys_needed: list[str] = []
    if modality == "visual":
        for hit in hits:
            for frame in hit.get("matched_frames", []):
                fk = SqliteVecStore.frame_key(hit["ad_id"], int(frame["frame_index"]))
                frame_keys_needed.append(fk)

    frame_vectors: dict[str, list[float]] = {}
    if frame_keys_needed and modality == "visual":
        frame_vectors = store.get_frame_vectors_batch(frame_keys_needed)

    filtered: list[dict[str, Any]] = []
    for hit in hits:
        ad_sim: float | None = None
        best_frame_sim: float | None = None

        stored_ad = ad_getter(hit["ad_id"])
        if stored_ad is not None:
            ad_sim = cosine_similarity(query_vector, stored_ad)

        if modality == "visual":
            for frame in hit.get("matched_frames", []):
                fk = SqliteVecStore.frame_key(hit["ad_id"], int(frame["frame_index"]))
                fv = frame_vectors.get(fk)
                if fv is not None:
                    frame_sim = cosine_similarity(query_vector, fv)
                    if best_frame_sim is None or frame_sim > best_frame_sim:
                        best_frame_sim = frame_sim

        best_sim = ad_sim
        if best_frame_sim is not None and (best_sim is None or best_frame_sim > best_sim):
            best_sim = best_frame_sim

        if best_sim is not None and best_sim >= min_score:
            hit = {**hit, "score": round(best_sim, 4)}
            filtered.append(hit)
    return filtered
