from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from ad_classifier.api.deps import get_config, open_request_db
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.embeddings.image.siglip2 import SigLIP2ImageEmbedder
from ad_classifier.embeddings.text.sentence_transformer import SentenceTransformerEmbedder
from ad_classifier.search.fts import fts_search_expanded
from ad_classifier.search.hybrid import hybrid_search
from ad_classifier.search.results import (
    cosine_similarity,
    filter_by_min_score,
    filter_by_min_score_any,
    filter_by_query_intent,
    filter_hits,
    group_frame_hits,
    rerank_hits,
)
from ad_classifier.search.rrf import rrf_fuse
from ad_classifier.search.visual_query import expand_visual_query_texts
from ad_classifier.vectors.sqlite_vec import SqliteVecStore

router = APIRouter(tags=["search"])


@lru_cache(maxsize=4)
def _text_embedder(model: str, device: str) -> SentenceTransformerEmbedder:
    return SentenceTransformerEmbedder(model, device)


@lru_cache(maxsize=2)
def _visual_text_embedder(model: str, device: str) -> SigLIP2ImageEmbedder:
    return SigLIP2ImageEmbedder(model, device)


@router.get("/search")
def search_ads(
    request: Request,
    q: str | None = None,
    mode: Literal["keyword", "text", "visual", "hybrid", "visual_hybrid"] = "hybrid",
    ad_id: str | None = None,
    brand: str | None = None,
    promotion: str | None = None,
    category: str | None = None,
    risk_label: str | None = None,
    status: str | None = None,
    rerank: bool = Query(default=True),
    k: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    config = get_config(request)
    conn = open_request_db(request)
    try:
        store = SqliteVecStore(
            conn,
            text_dim=config.vector_store.text_dim,
            visual_dim=config.vector_store.visual_dim,
        )
        load_sqlite_vec(conn)
        store.ensure_tables()

        if mode == "keyword":
            if not q:
                raise HTTPException(status_code=400, detail="q is required for keyword search")
            hits = [
                {"ad_id": ad_id, "score": score, "source": "keyword"}
                for ad_id, score in fts_search_expanded(conn, q, limit=k * 8)
            ]
            hits = filter_by_query_intent(conn, hits, q)
            hits = filter_hits(
                conn,
                hits,
                brand=brand,
                promotion=promotion,
                category=category,
                risk_label=risk_label,
                status=status,
                k=k,
            )
            return {"mode": mode, "items": _hydrate_hits(conn, hits)}

        if mode == "hybrid" and q and not ad_id:
            keyword_hits = [
                {"ad_id": ad_id, "score": score, "source": "keyword"}
                for ad_id, score in fts_search_expanded(conn, q, limit=k * 8)
            ]
            keyword_hits = filter_by_query_intent(conn, keyword_hits, q)
            if keyword_hits:
                if rerank:
                    keyword_hits = rerank_hits(conn, keyword_hits, q)
                keyword_hits = filter_hits(
                    conn,
                    keyword_hits,
                    brand=brand,
                    promotion=promotion,
                    category=category,
                    risk_label=risk_label,
                    status=status,
                    k=k,
                )
                return {
                    "mode": mode,
                    "strategy": "keyword_first",
                    "filtered_count": 0,
                    "items": _hydrate_hits(conn, keyword_hits),
                }

        if mode == "visual":
            visual_k = _visual_candidate_k(k)
            if ad_id:
                vector = store.get_visual(ad_id)
                vectors = [vector] if vector is not None else []
                source = "visual_seed"
            elif q:
                try:
                    vectors = _embed_visual_queries(config, q)
                except Exception as exc:
                    raise HTTPException(
                        status_code=503,
                        detail=f"visual text embedder unavailable: {exc}",
                    ) from exc
                source = "visual_text"
            else:
                raise HTTPException(
                    status_code=400,
                    detail="q or ad_id is required for visual search",
                )
            if not vectors:
                raise HTTPException(status_code=404, detail="visual vector not found")
            hits = _visual_hits_for_vectors(store, vectors, k=visual_k, source=source, ad_id=ad_id)
            if not hits:
                hits = _ad_visual_hits_for_vectors(
                    store, vectors, k=visual_k, source=source, ad_id=ad_id
                )
            total_before = len(hits)
            hits = filter_by_min_score_any(
                store,
                hits,
                vectors,
                min_score=config.search.visual_min_score,
                modality="visual",
            )
            filtered_count = total_before - len(hits)
            hits = _sort_visual_scores(hits)
            if rerank and q:
                hits = rerank_hits(conn, hits, q)
            hits = filter_by_query_intent(conn, hits, q)
            hits = filter_hits(
                conn,
                hits,
                brand=brand,
                promotion=promotion,
                category=category,
                risk_label=risk_label,
                status=status,
                k=k,
            )
            return {
                "mode": mode,
                "strategy": "frame_visual",
                "filtered_count": filtered_count,
                "items": _hydrate_hits(conn, hits),
            }

        query_vector = None
        if ad_id:
            query_vector = store.get_text(ad_id)
        elif q and mode in ("text", "hybrid"):
            try:
                query_vector = _text_embedder(
                    config.text_embedder.model,
                    config.text_embedder.device,
                ).embed(q)
            except Exception as exc:
                if mode == "text":
                    raise HTTPException(
                        status_code=503,
                        detail=f"text embedder unavailable: {exc}",
                    ) from exc
                query_vector = None

        if mode == "text":
            if query_vector is None:
                raise HTTPException(
                    status_code=400, detail="q or ad_id is required for text search"
                )
            hits = [
                {"ad_id": found_id, "distance": distance, "source": "text_vector"}
                for found_id, distance in store.search_text(query_vector, k=k * 8 + 1)
                if found_id != ad_id
            ]
            total_before = len(hits)
            hits = filter_by_min_score(
                store, hits, query_vector, min_score=config.search.text_min_score, modality="text"
            )
            filtered_count = total_before - len(hits)
            hits = filter_hits(
                conn,
                hits,
                brand=brand,
                promotion=promotion,
                category=category,
                risk_label=risk_label,
                status=status,
                k=k,
            )
            return {
                "mode": mode,
                "filtered_count": filtered_count,
                "items": _hydrate_hits(conn, hits),
            }

        if mode == "visual_hybrid":
            visual_k = _visual_candidate_k(k)
            if not q:
                raise HTTPException(
                    status_code=400, detail="q is required for visual hybrid search"
                )
            try:
                vectors = _embed_visual_queries(config, q)
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"visual text embedder unavailable: {exc}",
                ) from exc
            if not vectors:
                raise HTTPException(status_code=503, detail="visual text embedder unavailable")
            fts_results = fts_search_expanded(conn, q, limit=k * 8)
            fts_ids = {ad_id for ad_id, _score in fts_results}
            fts_rank = {ad_id: i + 1 for i, (ad_id, _score) in enumerate(fts_results)}
            visual_hits = _visual_hits_for_vectors(store, vectors, k=visual_k, source="visual_text")
            if not visual_hits:
                visual_hits = _ad_visual_hits_for_vectors(
                    store, vectors, k=visual_k, source="visual_text"
                )
            total_before = len(visual_hits)
            visual_hits = filter_by_min_score_any(
                store,
                visual_hits,
                vectors,
                min_score=config.search.visual_hybrid_min_score,
                modality="visual",
            )
            filtered_count = total_before - len(visual_hits)
            visual_hits = _sort_visual_scores(visual_hits)
            visual_by_ad = {hit["ad_id"]: hit for hit in visual_hits}
            fused = rrf_fuse(
                [ad_id for ad_id, _score in fts_results],
                [hit["ad_id"] for hit in visual_hits],
            )
            hits: list[dict[str, Any]] = []
            for found_id, rrf_score in fused:
                hit = dict(visual_by_ad.get(found_id, {"ad_id": found_id}))
                hit["rrf_score"] = rrf_score
                hit["fts_rank"] = fts_rank.get(found_id)
                has_fts = found_id in fts_ids
                has_visual = found_id in visual_by_ad
                if has_fts and has_visual:
                    hit["source"] = "keyword+visual"
                elif has_visual:
                    hit["source"] = "visual_text"
                else:
                    hit["source"] = "keyword"
                hits.append(hit)
            if rerank:
                hits = rerank_hits(conn, hits, q)
            hits = filter_by_query_intent(conn, hits, q)
            hits = filter_hits(
                conn,
                hits,
                brand=brand,
                promotion=promotion,
                category=category,
                risk_label=risk_label,
                status=status,
                k=k,
            )
            return {
                "mode": mode,
                "strategy": "visual_ocr_rrf",
                "filtered_count": filtered_count,
                "items": _hydrate_hits(conn, hits),
            }

        if not q and query_vector is None:
            raise HTTPException(status_code=400, detail="q or ad_id is required for hybrid search")
        hits = hybrid_search(
            conn,
            store,
            query_text=q,
            query_vector=query_vector,
            modality="text",
            k_fts=k * 4,
            k_vec=k * 4,
            k_final=k,
        )
        items: list[dict[str, Any]] = []
        for hit in hits:
            item = hit.model_dump(mode="json")
            if hit.fts_rank is not None and hit.vec_rank is not None:
                item["source"] = "keyword+vector"
            elif hit.fts_rank is not None:
                item["source"] = "keyword"
            else:
                item["source"] = "text_vector"
            items.append(item)
        filtered_count = 0
        if query_vector is not None:
            filtered: list[dict[str, Any]] = []
            for item in items:
                if item.get("fts_rank") is not None:
                    filtered.append(item)
                    continue
                stored = store.get_text(item["ad_id"])
                if stored is not None:
                    sim = cosine_similarity(query_vector, stored)
                    if sim < config.search.text_min_score:
                        filtered_count += 1
                        continue
                    item["score"] = round(sim, 4)
                filtered.append(item)
            items = filtered
        items = filter_by_query_intent(conn, items, q)
        items = filter_hits(
            conn,
            items,
            brand=brand,
            promotion=promotion,
            category=category,
            risk_label=risk_label,
            status=status,
            k=k,
        )
        return {
            "mode": mode,
            "strategy": "hybrid_rrf",
            "filtered_count": filtered_count,
            "items": _hydrate_hits(conn, items),
        }
    finally:
        conn.close()


def _embed_visual_queries(config, query: str) -> list[list[float]]:
    embedder = _visual_text_embedder(
        config.image_embedder.model,
        config.image_embedder.device,
    )
    texts = expand_visual_query_texts(query)
    if not texts:
        return []
    return [embedder.embed_text(text) for text in texts]


def _visual_candidate_k(k: int) -> int:
    return min(max(k * 32, 256), 2000)


def _visual_hits_for_vectors(
    store: SqliteVecStore,
    vectors: list[list[float]],
    *,
    k: int,
    source: str,
    ad_id: str | None = None,
) -> list[dict[str, Any]]:
    by_ad: dict[str, dict[str, Any]] = {}
    for vector in vectors:
        for hit in group_frame_hits(
            store.search_frame_visual(vector, k=k),
            source=source,
            exclude_ad_id=ad_id,
        ):
            _merge_visual_hit(by_ad, hit)
    return sorted(by_ad.values(), key=lambda row: float(row.get("distance", 999.0)))


def _ad_visual_hits_for_vectors(
    store: SqliteVecStore,
    vectors: list[list[float]],
    *,
    k: int,
    source: str,
    ad_id: str | None = None,
) -> list[dict[str, Any]]:
    by_ad: dict[str, dict[str, Any]] = {}
    for vector in vectors:
        for found_id, distance in store.search_visual(vector, k=k):
            if found_id == ad_id:
                continue
            _merge_visual_hit(
                by_ad,
                {"ad_id": found_id, "distance": distance, "source": source},
            )
    return sorted(by_ad.values(), key=lambda row: float(row.get("distance", 999.0)))


def _merge_visual_hit(by_ad: dict[str, dict[str, Any]], hit: dict[str, Any]) -> None:
    ad_id = str(hit["ad_id"])
    existing = by_ad.get(ad_id)
    if existing is None:
        by_ad[ad_id] = dict(hit)
        return
    if float(hit.get("distance", 999.0)) < float(existing.get("distance", 999.0)):
        existing["distance"] = hit.get("distance")
    frames = existing.setdefault("matched_frames", [])
    seen = {int(frame["frame_index"]) for frame in frames if frame.get("frame_index") is not None}
    for frame in hit.get("matched_frames", []):
        frame_index = int(frame["frame_index"])
        if frame_index not in seen and len(frames) < 3:
            frames.append(frame)
            seen.add(frame_index)


def _sort_visual_scores(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(hits, key=lambda row: float(row.get("score", -1.0)), reverse=True)


def _hydrate_hits(conn, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not hits:
        return []

    ad_ids = [hit["ad_id"] for hit in hits]
    placeholders = ", ".join("?" for _ in ad_ids)
    ad_rows = conn.execute(
        f"SELECT * FROM ads WHERE id IN ({placeholders})",
        ad_ids,
    ).fetchall()
    ads = {row["id"]: dict(row) for row in ad_rows}

    frame_rows = conn.execute(
        f"""
        SELECT ad_id, path, time_ms
        FROM (
          SELECT
            ad_id,
            path,
            time_ms,
            ROW_NUMBER() OVER (
              PARTITION BY ad_id
              ORDER BY kept DESC, frame_index ASC
            ) AS rn
          FROM frames
          WHERE ad_id IN ({placeholders})
        )
        WHERE rn = 1
        """,
        ad_ids,
    ).fetchall()
    frames = {row["ad_id"]: dict(row) for row in frame_rows}

    hydrated: list[dict[str, Any]] = []
    for hit in hits:
        ad = ads.get(hit["ad_id"])
        frame = frames.get(hit["ad_id"])
        matched_frames = hit.get("matched_frames") or []
        best_matched = matched_frames[0] if matched_frames else None
        hydrated.append(
            {
                **hit,
                "ad": ad,
                "thumbnail_path": (
                    best_matched.get("path") if best_matched else frame["path"] if frame else None
                ),
                "thumbnail_time_ms": (
                    best_matched.get("time_ms")
                    if best_matched
                    else frame["time_ms"] if frame else None
                ),
            }
        )
    return hydrated
