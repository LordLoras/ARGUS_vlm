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
    mode: Literal["keyword", "text", "visual", "hybrid"] = "hybrid",
    ad_id: str | None = None,
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
                for ad_id, score in fts_search_expanded(conn, q, limit=k)
            ]
            return {"mode": mode, "items": _hydrate_hits(conn, hits)}

        if mode == "visual":
            if ad_id:
                vector = store.get_visual(ad_id)
                source = "visual_seed"
            elif q:
                vector = _visual_text_embedder(
                    config.image_embedder.model,
                    config.image_embedder.device,
                ).embed_text(q)
                source = "visual_text"
            else:
                raise HTTPException(
                    status_code=400,
                    detail="q or ad_id is required for visual search",
                )
            if vector is None:
                raise HTTPException(status_code=404, detail="visual vector not found")
            hits = [
                {"ad_id": found_id, "distance": distance, "source": source}
                for found_id, distance in store.search_visual(vector, k=k)
                if found_id != ad_id
            ]
            return {"mode": mode, "items": _hydrate_hits(conn, hits[:k])}

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
                for found_id, distance in store.search_text(query_vector, k=k + 1)
                if found_id != ad_id
            ]
            return {"mode": mode, "items": _hydrate_hits(conn, hits[:k])}

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
        return {"mode": mode, "strategy": "hybrid_rrf", "items": _hydrate_hits(conn, items)}
    finally:
        conn.close()


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
        hydrated.append(
            {
                **hit,
                "ad": ad,
                "thumbnail_path": frame["path"] if frame else None,
                "thumbnail_time_ms": frame["time_ms"] if frame else None,
            }
        )
    return hydrated
