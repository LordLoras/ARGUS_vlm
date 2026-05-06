from __future__ import annotations

import math

from ad_classifier.models.similarity import FieldDifference, SimilarAdRecord, SimilarityVerdict
from ad_classifier.pipeline.aggregation.models import RelatedAds, SimilarAd
from ad_classifier.vectors.sqlite_vec import SqliteVecStore


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _distance_to_similarity(distance: float) -> float:
    """Convert L2 distance (sqlite-vec default) to a 0-1 similarity score."""
    return max(0.0, 1.0 - distance / 2.0)


def find_similar_by_text(
    store: SqliteVecStore,
    ad_id: str,
    text_vector: list[float],
    *,
    k: int = 10,
    min_score: float = 0.70,
    exclude_self: bool = True,
) -> list[tuple[str, float]]:
    """Return (ad_id, text_score) pairs for ads similar by text embedding."""
    results = store.search_text(text_vector, k=k + (1 if exclude_self else 0))
    out = []
    for found_id, distance in results:
        if exclude_self and found_id == ad_id:
            continue
        score = _distance_to_similarity(distance)
        if score >= min_score:
            out.append((found_id, score))
    return out[:k]


def find_similar_by_visual(
    store: SqliteVecStore,
    ad_id: str,
    visual_vector: list[float],
    *,
    k: int = 10,
    min_score: float = 0.70,
    exclude_self: bool = True,
) -> list[tuple[str, float]]:
    """Return (ad_id, visual_score) pairs for ads similar by visual embedding."""
    results = store.search_visual(visual_vector, k=k + (1 if exclude_self else 0))
    out = []
    for found_id, distance in results:
        if exclude_self and found_id == ad_id:
            continue
        score = _distance_to_similarity(distance)
        if score >= min_score:
            out.append((found_id, score))
    return out[:k]


def enrich_related_ads(
    store: SqliteVecStore,
    ad_id: str,
    *,
    text_vector: list[float] | None = None,
    visual_vector: list[float] | None = None,
    k: int = 5,
    min_score: float = 0.70,
) -> RelatedAds:
    """A1.3: Build RelatedAds by combining text + visual similarity searches."""
    text_scores: dict[str, float] = {}
    visual_scores: dict[str, float] = {}

    if text_vector:
        for found_id, score in find_similar_by_text(store, ad_id, text_vector, k=k, min_score=min_score):
            text_scores[found_id] = score

    if visual_vector:
        for found_id, score in find_similar_by_visual(store, ad_id, visual_vector, k=k, min_score=min_score):
            visual_scores[found_id] = score

    all_ids = set(text_scores) | set(visual_scores)
    similar: list[SimilarAd] = []

    for found_id in all_ids:
        t = text_scores.get(found_id)
        v = visual_scores.get(found_id)
        scores = [s for s in (t, v) if s is not None]
        overall = sum(scores) / len(scores) if scores else 0.0

        similar.append(
            SimilarAd(
                ad_id=found_id,
                overall_score=round(overall, 4),
                text_score=round(t, 4) if t is not None else None,
                visual_score=round(v, 4) if v is not None else None,
                verdict="related",
            )
        )

    similar.sort(key=lambda x: x.overall_score, reverse=True)

    return RelatedAds(semantically_similar=similar[:k])
