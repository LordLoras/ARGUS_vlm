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
from ad_classifier.search.results import filter_hits, group_frame_hits, rerank_hits
from ad_classifier.search.rrf import rrf_fuse
from ad_classifier.search.visual_query import expand_visual_query_texts, mean_pool
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
    category: str | None = None,
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
            hits = filter_hits(conn, hits, brand=brand, category=category, status=status, k=k)
            return {"mode": mode, "items": _hydrate_hits(conn, hits)}

        if mode == "visual":
            if ad_id:
                vector = store.get_visual(ad_id)
                source = "visual_seed"
            elif q:
                try:
                    vector = _embed_visual_query(config, q)
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
            if vector is None:
                raise HTTPException(status_code=404, detail="visual vector not found")
            frame_hits = store.search_frame_visual(vector, k=k * 8)
            hits = group_frame_hits(frame_hits, source=source, exclude_ad_id=ad_id)
            if not hits:
                hits = [
                    {"ad_id": found_id, "distance": distance, "source": source}
                    for found_id, distance in store.search_visual(vector, k=k * 8)
                    if found_id != ad_id
                ]
            if rerank and q:
                hits = rerank_hits(conn, hits, q)
            hits = filter_hits(conn, hits, brand=brand, category=category, status=status, k=k)
            return {"mode": mode, "strategy": "frame_visual", "items": _hydrate_hits(conn, hits)}

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
            hits = filter_hits(conn, hits, brand=brand, category=category, status=status, k=k)
            return {"mode": mode, "items": _hydrate_hits(conn, hits)}

        if mode == "visual_hybrid":
            if not q:
                raise HTTPException(status_code=400, detail="q is required for visual hybrid search")
            try:
                vector = _embed_visual_query(config, q)
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"visual text embedder unavailable: {exc}",
                ) from exc
            if vector is None:
                raise HTTPException(status_code=503, detail="visual text embedder unavailable")
            fts_results = fts_search_expanded(conn, q, limit=k * 8)
            frame_hits = store.search_frame_visual(vector, k=k * 8)
            visual_hits = group_frame_hits(frame_hits, source="visual_text")
            if not visual_hits:
                visual_hits = [
                    {"ad_id": found_id, "distance": distance, "source": "visual_text"}
                    for found_id, distance in store.search_visual(vector, k=k * 8)
                ]
            fused = rrf_fuse(
                [ad_id for ad_id, _score in fts_results],
                [hit["ad_id"] for hit in visual_hits],
            )
            fts_rank = {found_id: index + 1 for index, (found_id, _score) in enumerate(fts_results)}
            visual_by_ad = {hit["ad_id"]: hit for hit in visual_hits}
            hits = []
            for found_id, rrf_score in fused:
                hit = dict(visual_by_ad.get(found_id, {"ad_id": found_id}))
                hit["rrf_score"] = rrf_score
                hit["fts_rank"] = fts_rank.get(found_id)
                if found_id in visual_by_ad:
                    hit["source"] = "keyword+visual"
                else:
                    hit["source"] = "keyword"
                hits.append(hit)
            if rerank:
                hits = rerank_hits(conn, hits, q)
            hits = filter_hits(conn, hits, brand=brand, category=category, status=status, k=k)
            return {
                "mode": mode,
                "strategy": "visual_ocr_rrf",
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
        items = filter_hits(conn, items, brand=brand, category=category, status=status, k=k)
        return {"mode": mode, "strategy": "hybrid_rrf", "items": _hydrate_hits(conn, items)}
    finally:
        conn.close()


def _embed_visual_query(config, query: str) -> list[float] | None:
    embedder = _visual_text_embedder(
        config.image_embedder.model,
        config.image_embedder.device,
    )
    texts = expand_visual_query_texts(query)
    if not texts:
        return None
    if hasattr(embedder, "embed_text_batch"):
        return mean_pool(embedder.embed_text_batch(texts))
    return mean_pool([embedder.embed_text(text) for text in texts])


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
