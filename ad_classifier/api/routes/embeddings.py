from __future__ import annotations

import logging
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, Query, Request

from ad_classifier.api.deps import get_config, open_request_db
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.vectors.store import deserialize_float32
from ad_classifier.vectors.sqlite_vec import SqliteVecStore

router = APIRouter(tags=["embeddings"])
log = logging.getLogger(__name__)


@router.get("/embeddings/scatter")
def embeddings_scatter(
    request: Request,
    type: Literal["text", "visual"] = "text",
    sample: int = Query(default=600, ge=10, le=2000),
) -> dict[str, Any]:
    config = get_config(request)
    conn = open_request_db(request)
    try:
        load_sqlite_vec(conn)
        store = SqliteVecStore(
            conn,
            text_dim=config.vector_store.text_dim,
            visual_dim=config.vector_store.visual_dim,
        )
        store.ensure_tables()

        table = "vec_ads_text" if type == "text" else "vec_ads_visual"
        rows = conn.execute(f"SELECT ad_id, embedding FROM {table}").fetchall()
        if not rows:
            return {"points": [], "categories": [], "total": 0, "sampled": 0, "type": type}

        ad_ids: list[str] = []
        vector_rows: list[list[float]] = []
        expected_dim = config.vector_store.text_dim if type == "text" else config.vector_store.visual_dim
        for row in rows:
            raw = row["embedding"]
            try:
                vector = (
                    deserialize_float32(bytes(raw))
                    if isinstance(raw, (bytes, bytearray, memoryview))
                    else list(raw)
                )
            except Exception:
                log.warning("failed to deserialize embedding for scatter", extra={"ad_id": row["ad_id"], "type": type})
                continue
            if len(vector) != expected_dim:
                log.warning(
                    "skipping embedding with unexpected dimension",
                    extra={"ad_id": row["ad_id"], "type": type, "dim": len(vector), "expected_dim": expected_dim},
                )
                continue
            ad_ids.append(row["ad_id"])
            vector_rows.append(vector)

        if not vector_rows:
            return {"points": [], "categories": [], "total": len(rows), "sampled": 0, "type": type}

        vectors = np.array(vector_rows, dtype=np.float32)

        if len(vectors) > sample:
            rng = np.random.default_rng(42)
            indices = rng.choice(len(vectors), sample, replace=False)
            vectors = vectors[indices]
            ad_ids = [ad_ids[i] for i in indices]

        # PCA to 3D
        coords = _pca_3d(vectors)

        # Hydrate with ad metadata
        placeholders = ", ".join("?" for _ in ad_ids)
        ad_rows = conn.execute(
            f"SELECT id, brand_name, primary_category, brand_confidence, promotion_name FROM ads WHERE id IN ({placeholders})",
            ad_ids,
        ).fetchall()
        ad_meta = {row[0]: dict(row) for row in ad_rows}

        categories_seen: set[str] = set()
        points: list[dict[str, Any]] = []
        for i, ad_id in enumerate(ad_ids):
            meta = ad_meta.get(ad_id, {})
            cat = meta.get("primary_category") or "uncategorized"
            categories_seen.add(cat)
            points.append({
                "id": ad_id,
                "x": float(coords[i, 0]),
                "y": float(coords[i, 1]),
                "z": float(coords[i, 2]),
                "category": cat,
                "confidence": meta.get("brand_confidence") or 0.5,
                "brand": meta.get("brand_name") or "",
                "label": meta.get("promotion_name") or meta.get("brand_name") or ad_id[:8],
            })

        return {
            "points": points,
            "categories": sorted(categories_seen),
            "total": len(rows),
            "sampled": len(points),
            "type": type,
        }
    finally:
        conn.close()


def _pca_3d(vectors: np.ndarray) -> np.ndarray:
    """Reduce vectors to 3D using PCA with normalization."""
    mean = vectors.mean(axis=0)
    centered = vectors - mean
    std = centered.std()
    if std > 0:
        centered = centered / std

    # SVD-based PCA (more numerically stable than covariance eigendecomposition)
    n = len(centered)
    if n < 3:
        padded = np.zeros((n, 3), dtype=np.float32)
        padded[:, :centered.shape[1]] = centered[:, :3] if centered.shape[1] >= 3 else np.pad(centered, ((0, 0), (0, 3 - centered.shape[1])))
        return padded

    try:
        u, s, vt = np.linalg.svd(centered, full_matrices=False)
        components = vt[:3]  # top 3 principal components
        projected = centered @ components.T
    except np.linalg.LinAlgError:
        log.warning("SVD failed, falling back to random projection")
        rng = np.random.default_rng(42)
        random_proj = rng.standard_normal((centered.shape[1], 3)).astype(np.float32)
        random_proj /= np.linalg.norm(random_proj, axis=0, keepdims=True)
        projected = centered @ random_proj

    # Scale to a nice viewing range
    for dim in range(3):
        col = projected[:, dim]
        lo, hi = col.min(), col.max()
        if hi - lo > 1e-6:
            projected[:, dim] = (col - lo) / (hi - lo) * 80 - 40

    return projected.astype(np.float32)
