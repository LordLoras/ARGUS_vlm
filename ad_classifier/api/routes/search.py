from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from ad_classifier.api.deps import get_config, open_request_db
from ad_classifier.embeddings.text.sentence_transformer import SentenceTransformerEmbedder
from ad_classifier.search.fts import fts_search
from ad_classifier.search.hybrid import hybrid_search
from ad_classifier.vectors.sqlite_vec import SqliteVecStore

router = APIRouter(tags=["search"])


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
        store.ensure_tables()

        if mode == "keyword":
            if not q:
                raise HTTPException(status_code=400, detail="q is required for keyword search")
            hits = [
                {"ad_id": ad_id, "score": score} for ad_id, score in fts_search(conn, q, limit=k)
            ]
            return {"mode": mode, "items": hits}

        if mode == "visual":
            if not ad_id:
                raise HTTPException(status_code=400, detail="ad_id is required for visual search")
            vector = store.get_visual(ad_id)
            if vector is None:
                raise HTTPException(status_code=404, detail="visual vector not found")
            hits = [
                {"ad_id": found_id, "distance": distance}
                for found_id, distance in store.search_visual(vector, k=k)
                if found_id != ad_id
            ]
            return {"mode": mode, "items": hits[:k]}

        query_vector = None
        if ad_id:
            query_vector = store.get_text(ad_id)
        elif q:
            query_vector = SentenceTransformerEmbedder(
                config.text_embedder.model,
                config.text_embedder.device,
            ).embed(q)

        if mode == "text":
            if query_vector is None:
                raise HTTPException(
                    status_code=400, detail="q or ad_id is required for text search"
                )
            hits = [
                {"ad_id": found_id, "distance": distance}
                for found_id, distance in store.search_text(query_vector, k=k + 1)
                if found_id != ad_id
            ]
            return {"mode": mode, "items": hits[:k]}

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
        return {"mode": mode, "items": [hit.model_dump(mode="json") for hit in hits]}
    finally:
        conn.close()
