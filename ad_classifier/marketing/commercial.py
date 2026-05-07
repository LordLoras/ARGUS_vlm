from __future__ import annotations

import re
from collections.abc import Iterable

from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import (
    CTAEntity,
    DisclaimerEntity,
    FinancingTerms,
    MarketingEntities,
    OfferEntity,
    PriceEntity,
)

_PRICE_PATTERN = re.compile(
    r"(?<![\w$])(?P<currency>\$)\s*(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)(?P<cents>\.\d{2})?(?!\w)",
    re.IGNORECASE,
)
_FINANCING_CONTEXT_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*%\s*(?:APR\s*)?financing\s+for\s+\d{1,3}\s+months?"
    r"(?:\s+on\s+select\s+[A-Z0-9][A-Z0-9\s&/-]{0,120})?",
    re.IGNORECASE,
)
_APR_PATTERN = re.compile(r"\b(?P<apr>\d+(?:\.\d+)?)\s*(?:%|％)\s*(?:APR)?\b", re.IGNORECASE)
_MONTHS_PATTERN = re.compile(r"\b(?:for\s+)?(?P<months>\d{1,3})\s+months?\b", re.IGNORECASE)
_EXPIRY_PATTERN = re.compile(
    r"\b(?:through|thru|ends|expires|by)\s+(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\b",
    re.IGNORECASE,
)
_CTA_PATTERN = re.compile(
    r"\b(call today|call now|visit\s+[a-z0-9.-]+\.[a-z]{2,}|shop now|learn more|buy now|get started|schedule now|book now|order now)\b",
    re.IGNORECASE,
)
_GARBLED_YEAR_PREFIX = re.compile(r"^\s*20[A-Z]{1,4}\d{1,4}\s+", re.IGNORECASE)
_MIN_COMMERCIAL_CONFIDENCE = 0.75
_PRICE_OFFER_TERMS = (
    "bonus cash",
    "cash allowance",
    "cash back",
    "financing",
    "apr",
    "just",
    "only",
    "starting at",
    "as low as",
    "per month",
    "/month",
    "off",
    "savings",
)
_DISCLAIMER_TERMS = (
    "well-qualified",
    "not all buyers",
    "offer excludes",
    "offers exclude",
    "msrp excludes",
    "dealer installed",
    "tax",
    "title",
    "license",
    "terms",
    "conditions",
    "see dealer",
    "expires",
)
_DISCLAIMER_START_PATTERN = re.compile(
    r"\b(?:offers?\s+exclude|for\s+well-qualified|not\s+all\s+buyers|tax|msrp\s+excludes|dealer\s+installed|expires)\b",
    re.IGNORECASE,
)


_DENSITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}

def normalize_ocr_text(text: str) -> str:
    text = text.replace("％", "%")
    text = re.sub(r"\bONSELECT\b", "ON SELECT", text, flags=re.IGNORECASE)
    text = re.sub(r"\bOffersexclude\b", "Offers exclude", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAPRfinancing\b", "APR financing", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def extract_commercial_entities(evidence_items: Iterable[EvidenceItem]) -> MarketingEntities:
    entities = MarketingEntities()
    seen_prices: set[str] = set()
    seen_offers: set[str] = set()
    seen_ctas: set[str] = set()
    seen_disclaimers: set[str] = set()

    for evidence in evidence_items:
        text = normalize_ocr_text(evidence.text)
        normalized_evidence = evidence.model_copy(update={"text": text})
        _extract_disclaimer_signal(
            text,
            normalized_evidence,
            entities,
            seen_disclaimers,
            allow_exact_text=_is_reliable_commercial_evidence(evidence),
        )
        if not _is_reliable_commercial_evidence(evidence):
            continue
        _extract_prices(text, normalized_evidence, entities, seen_prices, seen_offers)
        _extract_financing(text, normalized_evidence, entities, seen_offers)
        _extract_expiry(text, normalized_evidence, entities)
        _extract_ctas(text, normalized_evidence, entities, seen_ctas)

    return entities


def repair_products(products: list[str], brand_name: str | None) -> list[str]:
    repaired: list[str] = []
    for product in products:
        cleaned = _clean_entity_text(product)
        cleaned = _GARBLED_YEAR_PREFIX.sub("", cleaned).strip()
        if brand_name:
            cleaned = re.sub(
                rf"^\s*{re.escape(brand_name)}\s+",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
        cleaned = cleaned.strip(" ,-")
        if len(cleaned) < 2:
            continue
        if _compact_key(cleaned) not in {_compact_key(item) for item in repaired}:
            repaired.append(cleaned)
    return repaired


def merge_commercial_entities(
    base: MarketingEntities,
    extracted: MarketingEntities,
) -> MarketingEntities:
    base.products = _merge_strings(base.products, extracted.products)
    base.prices = [
        price
        for price in base.prices
        if price.text.strip() or (price.amount is not None and price.amount > 0)
    ]

    for price in extracted.prices:
        existing = {_price_key(item) for item in base.prices}
        if _price_key(price) not in existing:
            base.prices.append(price)

    for offer in extracted.offers:
        existing = {_compact_key(item.text) for item in base.offers}
        if _compact_key(offer.text) not in existing:
            base.offers.append(offer)

    for cta in extracted.ctas:
        existing = {_compact_key(item.text) for item in base.ctas}
        if _compact_key(cta.text) not in existing:
            base.ctas.append(cta)

    for disclaimer in extracted.disclaimers:
        existing = {_compact_key(item.text) for item in base.disclaimers}
        if _compact_key(disclaimer.text) not in existing:
            base.disclaimers.append(disclaimer)

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
    return base


def _extract_prices(
    text: str,
    evidence: EvidenceItem,
    entities: MarketingEntities,
    seen_prices: set[str],
    seen_offers: set[str],
) -> None:
    for match in _PRICE_PATTERN.finditer(text):
        amount = _parse_amount(match.group("amount"), match.group("cents"))
        if amount is None:
            continue
        context = _trim_offer_text(_context_window(text, match.start(), match.end()))
        if _is_financing_example(amount, context):
            continue
        price_text = f"{match.group('currency')}{match.group('amount')}{match.group('cents') or ''}"
        key = f"{match.group('currency')}:{amount:.2f}"
        if key not in seen_prices:
            seen_prices.add(key)
            entities.prices.append(
                PriceEntity(
                    text=price_text,
                    amount=amount,
                    currency=match.group("currency"),
                    evidence=[evidence.model_copy(update={"text": context or price_text})],
                )
            )
        if _looks_like_offer_context(context):
            _append_offer(context, evidence, entities, seen_offers)


def _extract_financing(
    text: str,
    evidence: EvidenceItem,
    entities: MarketingEntities,
    seen_offers: set[str],
) -> None:
    match = _FINANCING_CONTEXT_PATTERN.search(text)
    if match:
        offer_text = _trim_offer_text(match.group(0))
        _append_offer(offer_text, evidence, entities, seen_offers)

    if "financing" not in text.lower() and "apr" not in text.lower():
        return

    apr_match = _APR_PATTERN.search(text)
    months_match = _MONTHS_PATTERN.search(text)
    if entities.offer_terms.financing.text is None:
        if match:
            context = match.group(0)
        elif apr_match:
            context = _context_window(text, apr_match.start(), apr_match.end())
        else:
            context = text
        context = _trim_offer_text(context)
        entities.offer_terms.financing.text = context
        entities.offer_terms.financing.evidence = [evidence.model_copy(update={"text": context})]
    if apr_match and entities.offer_terms.financing.apr is None:
        entities.offer_terms.financing.apr = float(apr_match.group("apr"))
    if months_match and entities.offer_terms.financing.duration_months is None:
        entities.offer_terms.financing.duration_months = int(months_match.group("months"))


def _extract_expiry(text: str, evidence: EvidenceItem, entities: MarketingEntities) -> None:
    if entities.offer_terms.expiry.text is not None:
        return
    match = _EXPIRY_PATTERN.search(text)
    if not match:
        return
    expiry_text = match.group(0)
    entities.offer_terms.expiry.text = expiry_text
    entities.offer_terms.expiry.resolved_date = match.group("date")
    entities.offer_terms.expiry.evidence = [evidence.model_copy(update={"text": expiry_text})]


def _extract_ctas(
    text: str,
    evidence: EvidenceItem,
    entities: MarketingEntities,
    seen_ctas: set[str],
) -> None:
    for match in _CTA_PATTERN.finditer(text):
        cta_text = _clean_entity_text(match.group(0))
        key = _compact_key(cta_text)
        if key in seen_ctas:
            continue
        seen_ctas.add(key)
        entities.ctas.append(
            CTAEntity(text=cta_text, evidence=[evidence.model_copy(update={"text": cta_text})])
        )


def _extract_disclaimer_signal(
    text: str,
    evidence: EvidenceItem,
    entities: MarketingEntities,
    seen_disclaimers: set[str],
    *,
    allow_exact_text: bool,
) -> None:
    lower = text.lower()
    if not any(term in lower for term in _DISCLAIMER_TERMS):
        return

    density = "high" if len(text) >= 240 else "medium" if len(text) >= 120 else "low"
    entities.creative_attributes.disclaimer_density = _max_density(
        entities.creative_attributes.disclaimer_density,
        density,
    )

    if not allow_exact_text:
        return
    disclaimer_text = _clean_entity_text(_context_window(text, 0, min(len(text), 160), max_len=220))
    key = _compact_key(disclaimer_text)
    if key and key not in seen_disclaimers:
        seen_disclaimers.add(key)
        entities.disclaimers.append(
            DisclaimerEntity(
                text=disclaimer_text,
                evidence=[evidence.model_copy(update={"text": disclaimer_text})],
            )
        )


def _append_offer(
    text: str,
    evidence: EvidenceItem,
    entities: MarketingEntities,
    seen_offers: set[str],
) -> None:
    offer_text = _clean_entity_text(text)
    key = _compact_key(offer_text)
    if not key or key in seen_offers:
        return
    seen_offers.add(key)
    entities.offers.append(
        OfferEntity(text=offer_text, evidence=[evidence.model_copy(update={"text": offer_text})])
    )


def _parse_amount(amount: str, cents: str | None) -> float | None:
    try:
        if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", amount):
            return float(amount.replace(",", "").replace(".", ""))
        return float(amount.replace(",", "") + (cents or ""))
    except ValueError:
        return None


def _context_window(text: str, start: int, end: int, *, max_len: int = 180) -> str:
    if len(text) <= max_len:
        return text
    prefix = max(0, start - max_len // 3)
    suffix = min(len(text), end + (max_len - (end - start)))
    snippet = text[prefix:suffix].strip()
    if prefix > 0:
        snippet = "..." + snippet
    if suffix < len(text):
        snippet = snippet + "..."
    return snippet


def _trim_offer_text(text: str) -> str:
    match = _DISCLAIMER_START_PATTERN.search(text)
    if match and match.start() > 0:
        text = text[: match.start()]
    return _clean_entity_text(text)


def _clean_entity_text(text: str) -> str:
    text = normalize_ocr_text(text)
    text = re.sub(r"\s+([!?.,;:])", r"\1", text)
    return text.strip(" ,;:-")


def _looks_like_offer_context(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in _PRICE_OFFER_TERMS)


def _is_financing_example(amount: float, context: str) -> bool:
    lower = context.lower().replace(",", "")
    if "per month per $1000 financed" in lower:
        return True
    return amount == 1000 and "per $1000 financed" in lower


def _is_reliable_commercial_evidence(evidence: EvidenceItem) -> bool:
    return evidence.confidence is None or evidence.confidence >= _MIN_COMMERCIAL_CONFIDENCE


def _price_key(price: PriceEntity) -> str:
    if price.amount is not None:
        return f"{price.currency or ''}:{price.amount:.2f}"
    return _compact_key(price.text)


def _compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _merge_strings(left: list[str], right: list[str]) -> list[str]:
    merged = list(left)
    for item in right:
        if item and item not in merged:
            merged.append(item)
    return merged


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


def _max_density(left: str, right: str) -> str:
    return left if _DENSITY_RANK[left] >= _DENSITY_RANK[right] else right
