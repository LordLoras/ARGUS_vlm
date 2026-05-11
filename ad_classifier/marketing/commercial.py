from __future__ import annotations

from ad_classifier.marketing.ocr_normalize import normalize_ocr_text
from ad_classifier.marketing.offer_extraction import (
    _dedupe_disclaimers,
    _dedupe_offers,
    _fuzzy_dedupe_list,
    _fuzzy_dedupe_offers,
    extract_commercial_entities,
)
from ad_classifier.marketing.price_parsing import _normalize_price_entity, _price_key
from ad_classifier.marketing.product_utils import (
    _compact_key,
    _merge_products,
    repair_products,
)
from ad_classifier.models.marketing import (
    CampaignSuggestion,
    FinancingTerms,
    MarketingEntities,
)

_DENSITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def merge_commercial_entities(
    base: MarketingEntities,
    extracted: MarketingEntities,
) -> MarketingEntities:
    brand_name = base.brand.name or base.advertiser.brand_name

    vlm_has_products = bool(base.products)
    if vlm_has_products:
        base.products = repair_products(base.products, brand_name)
    else:
        extracted_products = repair_products(extracted.products, brand_name)
        base.products = extracted_products

    base.prices = [
        _normalize_price_entity(price)
        for price in base.prices
        if price.text.strip() or (price.amount is not None and price.amount > 0)
    ]

    if not base.prices:
        for price in extracted.prices:
            price = _normalize_price_entity(price)
            base.prices.append(price)

    if not base.offers:
        for offer in extracted.offers:
            base.offers.append(offer)
    else:
        upgraded = []
        for existing in base.offers:
            best = existing
            for candidate in extracted.offers:
                if _is_strict_upgrade(candidate.text, existing.text):
                    best = candidate
                    break
            upgraded.append(best)
        base.offers = upgraded
    base.offers = _dedupe_offers(base.offers)
    base.offers = _fuzzy_dedupe_offers(base.offers)

    if not base.ctas:
        for cta in extracted.ctas:
            base.ctas.append(cta)
    base.ctas = _fuzzy_dedupe_list(base.ctas)

    if not base.disclaimers:
        for disclaimer in extracted.disclaimers:
            base.disclaimers.append(disclaimer)
    base.disclaimers = _dedupe_disclaimers(base.disclaimers)

    if base.offer_terms.expiry.text is None:
        base.offer_terms.expiry = extracted.offer_terms.expiry

    base.offer_terms.financing = _merge_financing(
        base.offer_terms.financing,
        extracted.offer_terms.financing,
    )
    base.creative_attributes.disclaimer_density = _max_density(
        base.creative_attributes.disclaimer_density,
        extracted.creative_attributes.disclaimer_density,
    )
    if base.creative_attributes.format is None:
        base.creative_attributes.format = extracted.creative_attributes.format
    base.creative_attributes.end_card = (
        base.creative_attributes.end_card or extracted.creative_attributes.end_card
    )
    existing_names = {_compact_key(s.name) for s in base.campaign_suggestions}
    for suggestion in extracted.campaign_suggestions:
        if _compact_key(suggestion.name) not in existing_names:
            base.campaign_suggestions.append(suggestion)
            existing_names.add(_compact_key(suggestion.name))
    return base


def _max_density(left: str, right: str) -> str:
    return left if _DENSITY_RANK[left] >= _DENSITY_RANK[right] else right


def _is_strict_upgrade(candidate: str, existing: str) -> bool:
    if not candidate or not existing:
        return False
    if len(candidate) <= len(existing):
        return False
    existing_words = set(existing.lower().split())
    candidate_words = set(candidate.lower().split())
    return existing_words.issubset(candidate_words)


def _merge_financing(left: FinancingTerms, right: FinancingTerms) -> FinancingTerms:
    if left.text is None:
        return right
    if left.apr is None:
        left.apr = right.apr
    if left.monthly_payment is None:
        left.monthly_payment = right.monthly_payment
    if left.currency is None:
        left.currency = right.currency
    if left.duration_months in (None, 0):
        left.duration_months = right.duration_months
    if not left.evidence:
        left.evidence = list(right.evidence)
    return left


def _merge_strings(left: list[str], right: list[str]) -> list[str]:
    merged = list(left)
    for item in right:
        if item and item not in merged:
            merged.append(item)
    return merged
