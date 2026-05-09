from __future__ import annotations

import re
from collections.abc import Iterable

from ad_classifier.marketing.ocr_normalize import normalize_ocr_text
from ad_classifier.marketing.product_utils import _compact_key
from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import (
    CTAEntity,
    DisclaimerEntity,
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
_MIN_COMMERCIAL_CONFIDENCE = 0.75
_GENERIC_PRODUCT_PATTERN = re.compile(
    r"\b(?P<year>20\d{2})\s+(?P<name>[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z0-9-]+){0,4})\b"
)
_PRICE_OFFER_TERMS = (
    "bonus cash",
    "cash allowance",
    "cash back",
    "below msrp",
    "rebate",
    "discount",
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
    r"\b(?:offers?\s+exclude|for\s+well-qualified|not\s+all\s+buyers|"
    r"msrp\s+excludes|dealer\s+installed|expires|subject\s+to|cannot\s+be\s+combined|"
    r"see\s+dealer(?:ship)?|must\s+be\s+registered)\b",
    re.IGNORECASE,
)
_EXACT_DISCLAIMER_PATTERN = re.compile(
    r"\b(?:offers?\s+exclude|for\s+well-qualified|well-qualified|not\s+all\s+buyers|"
    r"msrp\s+excludes|dealer\s+installed|terms\s+(?:and|&)\s+conditions|"
    r"see\s+dealer|expires|through\s+[A-Z][A-Za-z]+|subject\s+to|"
    r"must\s+be\s+registered)\b",
    re.IGNORECASE,
)

_DENSITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def _max_density(left: str, right: str) -> str:
    return left if _DENSITY_RANK[left] >= _DENSITY_RANK[right] else right


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
        _extract_generic_products(text, entities)
        _extract_prices(text, normalized_evidence, entities, seen_prices, seen_offers)
        _extract_financing(text, normalized_evidence, entities, seen_offers)
        _extract_expiry(text, normalized_evidence, entities)
        _extract_ctas(text, normalized_evidence, entities, seen_ctas)

    return entities


def _extract_generic_products(text: str, entities: MarketingEntities) -> None:
    for match in _GENERIC_PRODUCT_PATTERN.finditer(text):
        name = match.group("name").strip()
        year = match.group("year")
        product = f"{year} {name}"
        if len(name) < 3:
            continue
        key = _compact_key(product)
        existing = {_compact_key(p) for p in entities.products}
        if key not in existing:
            entities.products.append(product)


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
    match = _EXACT_DISCLAIMER_PATTERN.search(text)
    if not match:
        return
    disclaimer_text = _clean_entity_text(text[match.start() : min(len(text), match.start() + 220)])
    if _is_garbled_disclaimer_text(disclaimer_text):
        return
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
    for term in _PRICE_OFFER_TERMS:
        if term == "off":
            if re.search(r"\boff\b", lower):
                return True
            continue
        if term in lower:
            return True
    return False


def _is_financing_example(amount: float, context: str) -> bool:
    lower = context.lower().replace(",", "")
    if "per month per $1000 financed" in lower:
        return True
    return amount == 1000 and "per $1000 financed" in lower


def _is_reliable_commercial_evidence(evidence: EvidenceItem) -> bool:
    return evidence.confidence is None or evidence.confidence >= _MIN_COMMERCIAL_CONFIDENCE


def _dedupe_offers(offers: list[OfferEntity]) -> list[OfferEntity]:
    merged: dict[str, OfferEntity] = {}
    order: list[str] = []
    for offer in offers:
        key = _offer_family_key(offer.text)
        current = merged.get(key)
        if current is None:
            merged[key] = offer
            order.append(key)
            continue
        if _offer_quality(offer, key) > _offer_quality(current, key):
            evidence = offer.evidence or current.evidence
            merged[key] = offer.model_copy(update={"evidence": evidence})
    return [merged[key] for key in order]


def _offer_family_key(text: str) -> str:
    lower = _clean_entity_text(text).lower()
    apr = re.search(r"\b(\d+(?:\.\d+)?)\s*%", lower)
    if "below msrp" in lower:
        amount = _money_key_before_phrase(lower, "below msrp") or _money_key_from_text(lower)
        return f"msrp_discount:{amount or ''}"
    amount = _money_key_from_text(lower)
    if "rebate" in lower:
        audience = ""
        if "military" in lower and "first responder" in lower:
            audience = "military_first_responder"
        elif "fca" in lower and ("owner" in lower or "lessee" in lower):
            audience = "fca_owner_lessee"
        return f"rebate:{amount or ''}:{audience}"
    if "bonus cash" in lower or "cash allowance" in lower:
        return f"cash_allowance:{amount or ''}"
    if "financing" in lower or "apr" in lower:
        return f"financing:{apr.group(1) if apr else ''}"
    if "monthly payment" in lower or "payments for" in lower:
        return "payment_deferral"
    if "sales tax" in lower:
        return "sales_tax"
    return _compact_key(text)


def _offer_quality(offer: OfferEntity, family_key: str) -> int:
    text = _clean_entity_text(offer.text)
    lower = text.lower()
    if family_key.startswith(("msrp_discount", "rebate", "cash_allowance")):
        score = 220
        if _money_key_from_text(lower):
            score += 30
        if "below msrp" in lower or "rebate" in lower or "cash allowance" in lower:
            score += 25
        if "military" in lower and "first responder" in lower:
            score += 25
        if offer.evidence and offer.evidence[0].source == "vlm":
            score += 100
        if len(text) <= 80:
            score += 80
        score -= len(text) // 3
        score -= max(0, len(text) - 80)
        if re.search(r"\bstk\s*#|\bstock\s*#", lower, re.IGNORECASE):
            score -= 40
        if "cannot be combined" in lower or "see dealer" in lower or "see dealership" in lower:
            score -= 80
        return score

    score = _offer_specificity(text)
    if offer.evidence and offer.evidence[0].source == "vlm":
        score += 100
    return score


def _offer_specificity(text: str) -> int:
    lower = text.lower()
    score = len(text)
    if "apr" in lower:
        score += 20
    if re.search(r"\b\d{1,3}\s+months?\b", lower):
        score += 15
    if re.search(r"\b\d+(?:\.\d+)?\s*%", lower):
        score += 10
    return score


def _money_key_from_text(text: str) -> str | None:
    match = re.search(r"\$\s*(\d{1,3}(?:[,.]\d{3})+|\d+)(?:\.\d{2})?", text)
    if not match:
        return None
    return _money_key_from_match(match)


def _money_key_before_phrase(text: str, phrase: str) -> str | None:
    phrase_index = text.find(phrase)
    if phrase_index < 0:
        return None
    matches = list(
        re.finditer(r"\$\s*(\d{1,3}(?:[,.]\d{3})+|\d+)(?:\.\d{2})?", text[:phrase_index])
    )
    if not matches:
        return None
    return _money_key_from_match(matches[-1])


def _money_key_from_match(match: re.Match[str]) -> str | None:
    amount = _parse_amount(match.group(1), None)
    if amount is None:
        return None
    return str(int(amount)) if float(amount).is_integer() else f"{amount:.2f}"


def _dedupe_disclaimers(disclaimers: list[DisclaimerEntity]) -> list[DisclaimerEntity]:
    merged: dict[str, DisclaimerEntity] = {}
    order: list[str] = []
    for disclaimer in disclaimers:
        key = _disclaimer_family_key(disclaimer.text)
        current = merged.get(key)
        if current is None:
            merged[key] = disclaimer
            order.append(key)
            continue
        if _disclaimer_quality(disclaimer) > _disclaimer_quality(current):
            evidence = disclaimer.evidence or current.evidence
            merged[key] = disclaimer.model_copy(update={"evidence": evidence})
    return [merged[key] for key in order]


def _disclaimer_family_key(text: str) -> str:
    lower = text.lower()
    if "apr financing" in lower and ("4xe" in lower or "well-qualified" in lower):
        return "apr_financing_terms"
    if "excludes leases" in lower or "offer not available" in lower:
        return "lease_exclusion"
    if "well-qualified" in lower and "stellantis" in lower:
        return "qualified_buyer_financing_terms"
    if "offer ends" in lower or "expires" in lower:
        return "offer_expiry"
    if "see dealer" in lower:
        return "dealer_details"
    compact = _compact_key(text)
    return compact[:120]


def _disclaimer_quality(disclaimer: DisclaimerEntity) -> int:
    text = _clean_entity_text(disclaimer.text)
    source = disclaimer.evidence[0].source if disclaimer.evidence else None
    score = 0
    if source == "vlm":
        score += 100
    if not text.startswith("..."):
        score += 20
    if "..." not in text:
        score += 10
    score -= text.count("|") * 10
    score -= text.count("***") * 10
    score -= max(0, len(text) - 220) // 10
    return score


def _is_garbled_disclaimer_text(text: str) -> bool:
    lower = text.lower()
    return bool(re.search(r"\b(?:sery|tfan|resi)\b", lower))


def _fuzzy_dedupe_offers(offers: list[OfferEntity]) -> list[OfferEntity]:
    if len(offers) <= 1:
        return offers
    result: list[OfferEntity] = []
    for offer in offers:
        key = _compact_key(offer.text)
        merged = False
        for i, existing in enumerate(result):
            existing_key = _compact_key(existing.text)
            if key == existing_key:
                merged = True
                break
            if _text_similarity_ratio(key, existing_key) >= 0.80:
                if len(offer.text) > len(existing.text):
                    result[i] = offer
                merged = True
                break
            fam_existing = _offer_family_key(existing.text)
            fam_new = _offer_family_key(offer.text)
            if fam_existing == fam_new and fam_new != _compact_key(offer.text):
                if _offer_quality(offer, fam_new) > _offer_quality(existing, fam_existing):
                    result[i] = offer
                merged = True
                break
        if not merged:
            result.append(offer)
    return result


def _fuzzy_dedupe_list(items: list[CTAEntity | DisclaimerEntity]) -> list[CTAEntity | DisclaimerEntity]:
    if len(items) <= 1:
        return items
    result: list[CTAEntity | DisclaimerEntity] = []
    for item in items:
        key = _compact_key(item.text)
        merged = False
        for i, existing in enumerate(result):
            existing_key = _compact_key(existing.text)
            if key == existing_key:
                merged = True
                break
            if _text_similarity_ratio(key, existing_key) >= 0.80:
                if len(item.text) > len(existing.text):
                    result[i] = item
                merged = True
                break
        if not merged:
            result.append(item)
    return result


def _text_similarity_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if not shorter:
        return 0.0
    shared = sum(1 for c in shorter if c in longer)
    return shared / max(len(longer), 1)
