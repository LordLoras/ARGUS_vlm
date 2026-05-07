from __future__ import annotations

import sqlite3
from typing import Literal

from pydantic import Field

from ad_classifier.models.common import StrictModel
from ad_classifier.search.fts import fts_search_expanded
from ad_classifier.search.rrf import rrf_fuse
from ad_classifier.vectors.sqlite_vec import SqliteVecStore


class HybridSearchResult(StrictModel):
    ad_id: str
    rrf_score: float = Field(ge=0.0)
    fts_rank: int | None = None
    vec_rank: int | None = None
    vec_distance: float | None = None


def hybrid_search(
    conn: sqlite3.Connection,
    store: SqliteVecStore,
    *,
    query_text: str | None = None,
    query_vector: list[float] | None = None,
    modality: Literal["text", "visual"] = "text",
    k_fts: int = 20,
    k_vec: int = 20,
    k_final: int = 10,
    rrf_k: int = 60,
) -> list[HybridSearchResult]:
    """Hybrid FTS5 + vector search with RRF fusion.

    At least one of query_text or query_vector must be provided.
    modality selects which vector index to query ("text" or "visual").
    """
    if query_text is None and query_vector is None:
        raise ValueError("Provide at least one of query_text or query_vector")

    fts_results: list[tuple[str, float]] = []
    vec_results: list[tuple[str, float]] = []

    if query_text:
        try:
            fts_results = fts_search_expanded(conn, query_text, limit=k_fts)
        except Exception:
            fts_results = []

    if query_vector:
        if modality == "visual":
            vec_results = store.search_visual(query_vector, k=k_vec)
        else:
            vec_results = store.search_text(query_vector, k=k_vec)

    fts_ids = [r[0] for r in fts_results]
    vec_ids = [r[0] for r in vec_results]

    lists = [lst for lst in (fts_ids, vec_ids) if lst]
    if not lists:
        return []

    fused = rrf_fuse(*lists, k=rrf_k)[:k_final]

    fts_rank_map = {ad_id: i + 1 for i, (ad_id, _) in enumerate(fts_results)}
    vec_rank_map = {ad_id: i + 1 for i, (ad_id, _) in enumerate(vec_results)}
    vec_dist_map = {ad_id: dist for ad_id, dist in vec_results}

    return [
        HybridSearchResult(
            ad_id=ad_id,
            rrf_score=score,
            fts_rank=fts_rank_map.get(ad_id),
            vec_rank=vec_rank_map.get(ad_id),
            vec_distance=vec_dist_map.get(ad_id),
        )
        for ad_id, score in fused
    ]
