from __future__ import annotations

import math
from typing import Any

from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.models.marketing import MarketingEntities
from ad_classifier.models.similarity import FieldDifference, SimilarityVerdict
from ad_classifier.pipeline.aggregation.models import RelatedAds, SimilarAd
from ad_classifier.vectors.sqlite_vec import SqliteVecStore


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _score_cosine(query_vector: list[float], found_vector: list[float] | None) -> float | None:
    if found_vector is None:
        return None
    return max(0.0, min(1.0, cosine_similarity(query_vector, found_vector)))


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
    for found_id, _distance in results:
        if exclude_self and found_id == ad_id:
            continue
        score = _score_cosine(text_vector, store.get_text(found_id))
        if score is not None and score >= min_score:
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
    for found_id, _distance in results:
        if exclude_self and found_id == ad_id:
            continue
        score = _score_cosine(visual_vector, store.get_visual(found_id))
        if score is not None and score >= min_score:
            out.append((found_id, score))
    return out[:k]


def _strings(values: list[Any]) -> list[str]:
    return [str(value) for value in values if value]


def _brand_strings(entities: MarketingEntities | None) -> tuple[str | None, list[str]]:
    if entities is None:
        return None, []
    return entities.brand.name if entities.brand else None, _strings(entities.products)


def _price_strings(entities: MarketingEntities | None) -> list[str]:
    if entities is None:
        return []
    return [price.text for price in entities.prices if price.text]


def _offer_strings(entities: MarketingEntities | None) -> list[str]:
    if entities is None:
        return []
    return [offer.text for offer in entities.offers if offer.text]


def _diff_field(field: str, left: Any, right: Any) -> FieldDifference | None:
    if left == right or (not left and not right):
        return None
    return FieldDifference(field=field, left=left, right=right)


def _classify_verdict(
    overall: float,
    *,
    same_brand: bool,
    same_products: bool,
    same_offer: bool,
    same_subcategory: bool = False,
) -> SimilarityVerdict:
    if overall >= 0.95 and same_brand and same_products and same_offer:
        return "near_duplicate"
    if same_brand and same_products and not same_offer and overall >= 0.75:
        return "same_campaign_different_offer"
    if same_brand and not same_products and overall >= 0.75:
        return "same_campaign_different_sku"
    if not same_brand and overall >= 0.75:
        return "similar_messaging_different_brand"
    if overall >= 0.55:
        return "related"
    return "unrelated"


def _build_differences_and_verdict(
    store: SqliteVecStore,
    ad_id: str,
    found_id: str,
    overall: float,
) -> tuple[SimilarityVerdict, list[dict]]:
    marketing_repo = MarketingEntityRepository(store.conn)
    left_marketing = marketing_repo.get(ad_id)
    right_marketing = marketing_repo.get(found_id)
    l_brand, l_products = _brand_strings(left_marketing)
    r_brand, r_products = _brand_strings(right_marketing)
    l_prices = _price_strings(left_marketing)
    r_prices = _price_strings(right_marketing)
    l_offers = _offer_strings(left_marketing)
    r_offers = _offer_strings(right_marketing)

    classifications = ClassificationRepository(store.conn)
    l_class = classifications.get(ad_id)
    r_class = classifications.get(found_id)
    l_category = l_class.primary_category if l_class else None
    r_category = r_class.primary_category if r_class else None

    l_sub = left_marketing.subcategory if left_marketing else None
    r_sub = right_marketing.subcategory if right_marketing else None

    differences = [
        diff.model_dump()
        for diff in (
            _diff_field("brand", l_brand, r_brand),
            _diff_field("subcategory", l_sub, r_sub),
            _diff_field("products", l_products, r_products),
            _diff_field("prices", l_prices, r_prices),
            _diff_field("offers", l_offers, r_offers),
            _diff_field("primary_category", l_category, r_category),
        )
        if diff is not None
    ]
    same_brand = bool(l_brand) and l_brand == r_brand
    same_products = sorted(l_products) == sorted(r_products) and bool(l_products)
    same_offer = sorted(l_offers) == sorted(r_offers) and bool(l_offers)
    return (
        _classify_verdict(
            overall,
            same_brand=same_brand,
            same_products=same_products,
            same_offer=same_offer,
        ),
        differences,
    )


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
        if t is None and text_vector:
            t = _score_cosine(text_vector, store.get_text(found_id))
        if v is None and visual_vector:
            v = _score_cosine(visual_vector, store.get_visual(found_id))
        scores = [s for s in (t, v) if s is not None]
        overall = sum(scores) / len(scores) if scores else 0.0
        verdict, differences = _build_differences_and_verdict(store, ad_id, found_id, overall)

        similar.append(
            SimilarAd(
                ad_id=found_id,
                overall_score=round(overall, 4),
                text_score=round(t, 4) if t is not None else None,
                visual_score=round(v, 4) if v is not None else None,
                verdict=verdict,
                differences=differences,
            )
        )

    similar.sort(key=lambda x: x.overall_score, reverse=True)

    return RelatedAds(semantically_similar=similar[:k])
