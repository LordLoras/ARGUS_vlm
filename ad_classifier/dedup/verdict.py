from __future__ import annotations

from ad_classifier.models.similarity import SimilarityVerdict


def classify_verdict(
    overall: float,
    *,
    same_brand: bool,
    same_products: bool,
    same_offer: bool,
    same_subcategory: bool = False,
) -> SimilarityVerdict | None:
    if overall < 0.70:
        return None
    if overall >= 0.95 and same_brand and same_products and same_offer:
        return "near_duplicate"
    if same_brand and same_products and not same_offer and overall >= 0.75:
        return "same_campaign_different_offer"
    if same_brand and not same_products and overall >= 0.75:
        return "same_campaign_different_sku"
    if not same_brand and same_subcategory and overall >= 0.75:
        return "similar_messaging_different_brand"
    if overall >= 0.70:
        return "related"
    return None
