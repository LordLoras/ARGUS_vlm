from __future__ import annotations

import re
from collections.abc import Iterable

from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import (
    CampaignSignals,
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
_DECLARATION_DEALS_PATTERN = re.compile(
    r"\bdeclaration\s+of\s+(?:deals|teels)\b|\bdeclaration\s+ofdeals\b",
    re.IGNORECASE,
)
_AMERICA_250_PATTERN = re.compile(r"\bamerica\s*250\b", re.IGNORECASE)
_ONLY_ONE_PATTERN = re.compile(r"\bthere'?s\s+only\s+one\b", re.IGNORECASE)
_SHARED_JEEP_MODELS_PATTERN = re.compile(
    r"\b(?P<year>20\d{2})\s+(?:JEEP\s+)?GRAND\s+CHEROKEE\s+AND\s+GLADIATOR\s+MODELS?\b",
    re.IGNORECASE,
)
_JEEP_PRODUCT_PATTERN = re.compile(
    r"\b(?P<year>20\d{2})\s+(?:JEEP\s+)?(?P<model>GRAND\s+CHEROKEE|GLADIATOR|WRANGLER)"
    r"(?P<trims>(?:\s+(?:SPORT\s+S|4-DOOR|4X4|LIMITED|RUBICON|SAHARA|SUMMIT|SPORT|392|X)){0,8})",
    re.IGNORECASE,
)
_CHRYSLER_PRODUCT_PATTERN = re.compile(
    r"\b(?P<year>20\d{2})\s+(?:CHRYSLER\s+)?(?P<model>PACIFICA)"
    r"(?P<trims>(?:\s+(?:LIMITED|PINNACLE|SELECT|TOURING|HYBRID|AWD|FWD)){0,8})",
    re.IGNORECASE,
)
_GARBLED_YEAR_PREFIX = re.compile(r"^\s*20[A-Z]{1,4}\d{1,4}\s+", re.IGNORECASE)
_GENERIC_VEHICLE_MAKE_KEYS = {
    "jeep",
    "chrysler",
    "dodge",
    "ram",
    "fiat",
    "alfaromeo",
}
_MIN_COMMERCIAL_CONFIDENCE = 0.75
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

def normalize_ocr_text(text: str) -> str:
    text = text.replace("％", "%")
    text = re.sub(r"\$(\d{1,3})\.(\d{3})(?!\d)", r"$\1,\2", text)
    text = re.sub(r"\bDickPoe\b", "Dick Poe", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(20\d{2})(?=JEEP)", r"\1 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(20\d{2})(?=CHRYSLER)", r"\1 ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bJEEP(?=GRAND|WRANGLER|GLADIATOR)", "JEEP ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCHRYSLER(?=PACIFICA)", "CHRYSLER ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bGRANDCHEROKEE\b", "GRAND CHEROKEE", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCHRYSLERPACIFICA\b", "CHRYSLER PACIFICA", text, flags=re.IGNORECASE)
    text = re.sub(r"\bWRANGLER(?=4-DOOR)", "WRANGLER ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bLIMITED(?=4X4|4x4)", "LIMITED ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bPACIFICA(?=\$)", "PACIFICA ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bBELOWMSRP\b", "BELOW MSRP", text, flags=re.IGNORECASE)
    text = re.sub(r"\bREBAT\b", "REBATE", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMILITARY&FIRSTRESPONDER\b", "MILITARY & FIRST RESPONDER", text, flags=re.IGNORECASE)
    text = re.sub(r"\bFIRSTRESPONDER\b", "FIRST RESPONDER", text, flags=re.IGNORECASE)
    text = re.sub(r"\bONSELECT\b", "ON SELECT", text, flags=re.IGNORECASE)
    text = re.sub(r"\bOffersexclude\b", "Offers exclude", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAPRfinancing\b", "APR financing", text, flags=re.IGNORECASE)
    text = re.sub(r"\bDUEAT\b", "DUE AT", text, flags=re.IGNORECASE)
    text = re.sub(r"\bLEASEDETAILS\b", "LEASE DETAILS", text, flags=re.IGNORECASE)
    text = re.sub(r"\bCALL(?=\d)", "CALL ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\d{1,3})MOS\b", r"\1 MOS", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=[a-z])\.(?=[A-Z0-9])", ". ", text)
    text = re.sub(r"(?<=\d)\.(?=[A-Z])", ". ", text)
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
        _extract_campaign_signals(text, normalized_evidence, entities)
        _extract_vehicle_products(text, entities)
        _extract_prices(text, normalized_evidence, entities, seen_prices, seen_offers)
        _extract_financing(text, normalized_evidence, entities, seen_offers)
        _extract_expiry(text, normalized_evidence, entities)
        _extract_ctas(text, normalized_evidence, entities, seen_ctas)

    return entities


def repair_products(products: list[str], brand_name: str | None) -> list[str]:
    cleaned_items: list[str] = []
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
            cleaned = re.sub(
                rf"^\s*(20\d{{2}})\s+{re.escape(brand_name)}\s+",
                r"\1 ",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
        cleaned = cleaned.strip(" ,-")
        if len(cleaned) < 2:
            continue
        cleaned_items.append(cleaned)

    has_specific_vehicle = any(_is_specific_vehicle_product(item) for item in cleaned_items)
    brand_key = _compact_key(brand_name or "")
    for cleaned in cleaned_items:
        if _is_generic_vehicle_make_product(cleaned, brand_key, has_specific_vehicle):
            continue
        if _compact_key(cleaned) not in {_compact_key(item) for item in repaired}:
            repaired.append(cleaned)
    return repaired


def merge_commercial_entities(
    base: MarketingEntities,
    extracted: MarketingEntities,
) -> MarketingEntities:
    base.products = _merge_products(base.products, extracted.products)
    base.products = repair_products(base.products, base.brand.name or base.advertiser.brand_name)
    base.prices = [
        _normalize_price_entity(price)
        for price in base.prices
        if price.text.strip() or (price.amount is not None and price.amount > 0)
    ]

    for price in extracted.prices:
        price = _normalize_price_entity(price)
        existing = {_price_key(item) for item in base.prices}
        if _price_key(price) not in existing:
            base.prices.append(price)

    for offer in extracted.offers:
        existing = {_compact_key(item.text) for item in base.offers}
        if _compact_key(offer.text) not in existing:
            base.offers.append(offer)
    base.offers = _dedupe_offers(base.offers)

    base.offers = _fuzzy_dedupe_offers(base.offers)

    for cta in extracted.ctas:
        existing = {_compact_key(item.text) for item in base.ctas}
        if _compact_key(cta.text) not in existing:
            base.ctas.append(cta)

    base.ctas = _fuzzy_dedupe_list(base.ctas)

    for disclaimer in extracted.disclaimers:
        existing = {_compact_key(item.text) for item in base.disclaimers}
        if _compact_key(disclaimer.text) not in existing:
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
    base.campaign_signals = _merge_campaign_signals(
        base.campaign_signals,
        extracted.campaign_signals,
    )
    return base


def _extract_campaign_signals(
    text: str,
    evidence: EvidenceItem,
    entities: MarketingEntities,
) -> None:
    if _DECLARATION_DEALS_PATTERN.search(text):
        _fill_campaign_signal(
            entities.campaign_signals,
            "creative_variant",
            "Declaration of Deals",
            evidence.model_copy(update={"text": "Declaration of Deals"}),
        )
        _fill_campaign_signal(
            entities.campaign_signals,
            "campaign_theme",
            "Declaration of Deals",
            evidence.model_copy(update={"text": "Declaration of Deals"}),
        )
        entities.creative_attributes.end_card = True
        if entities.creative_attributes.format is None:
            entities.creative_attributes.format = "offer_end_card"

    if _AMERICA_250_PATTERN.search(text):
        _fill_campaign_signal(
            entities.campaign_signals,
            "campaign_theme",
            "America 250 / Declaration of Deals",
            evidence.model_copy(update={"text": "America 250"}),
        )

    if _ONLY_ONE_PATTERN.search(text):
        _fill_campaign_signal(
            entities.campaign_signals,
            "slogan",
            "There's only one",
            evidence.model_copy(update={"text": "There's only one"}),
        )


def _fill_campaign_signal(
    campaign: CampaignSignals,
    field: str,
    value: str,
    evidence: EvidenceItem,
) -> None:
    if getattr(campaign, field) is None:
        setattr(campaign, field, value)
    if not any(item.text == evidence.text and item.time_ms == evidence.time_ms for item in campaign.evidence):
        campaign.evidence.append(evidence)


def _extract_vehicle_products(text: str, entities: MarketingEntities) -> None:
    if _is_exclusion_context(text) or not _is_vehicle_offer_context(text):
        return
    for match in _SHARED_JEEP_MODELS_PATTERN.finditer(text):
        year = match.group("year")
        _append_product(entities, f"{year} Grand Cherokee")
        _append_product(entities, f"{year} Gladiator")

    for match in _JEEP_PRODUCT_PATTERN.finditer(text):
        product = _format_jeep_product(
            match.group("year"),
            match.group("model"),
            match.group("trims") or "",
        )
        _append_product(entities, product)

    for match in _CHRYSLER_PRODUCT_PATTERN.finditer(text):
        product = _format_chrysler_product(
            match.group("year"),
            match.group("model"),
            match.group("trims") or "",
        )
        _append_product(entities, product)


def _format_jeep_product(year: str, model: str, trims: str) -> str:
    model_key = re.sub(r"\s+", " ", model.strip().upper())
    model_text = {
        "GRAND CHEROKEE": "Grand Cherokee",
        "GLADIATOR": "Gladiator",
        "WRANGLER": "Wrangler",
    }[model_key]
    trim_tokens = re.sub(r"\s+", " ", trims.strip().upper())
    trim_tokens = trim_tokens.replace("4X4", "4x4")
    replacements = {
        "SPORT S": "Sport S",
        "4-DOOR": "4-Door",
        "4x4": "4x4",
        "LIMITED": "Limited",
        "RUBICON": "Rubicon",
        "SAHARA": "Sahara",
        "SUMMIT": "Summit",
        "SPORT": "Sport",
        "392": "392",
        "X": "X",
    }
    trim_matches: list[tuple[int, int, str]] = []
    for raw, formatted in replacements.items():
        for match in re.finditer(rf"\b{re.escape(raw)}\b", trim_tokens):
            trim_matches.append((match.start(), match.end(), formatted))
    trim_parts: list[str] = []
    consumed_until = -1
    for start, end, formatted in sorted(trim_matches, key=lambda item: (item[0], -(item[1] - item[0]))):
        if start < consumed_until:
            continue
        trim_parts.append(formatted)
        consumed_until = end
    suffix = f" {' '.join(trim_parts)}" if trim_parts else ""
    return f"{year} {model_text}{suffix}".strip()


def _format_chrysler_product(year: str, model: str, trims: str) -> str:
    model_key = re.sub(r"\s+", " ", model.strip().upper())
    model_text = {"PACIFICA": "Chrysler Pacifica"}[model_key]
    trim_tokens = re.sub(r"\s+", " ", trims.strip().upper())
    replacements = {
        "LIMITED": "Limited",
        "PINNACLE": "Pinnacle",
        "SELECT": "Select",
        "TOURING": "Touring",
        "HYBRID": "Hybrid",
        "AWD": "AWD",
        "FWD": "FWD",
    }
    trim_parts: list[str] = []
    for raw, formatted in replacements.items():
        if re.search(rf"\b{re.escape(raw)}\b", trim_tokens) and formatted not in trim_parts:
            trim_parts.append(formatted)
    suffix = f" {' '.join(trim_parts)}" if trim_parts else ""
    return f"{year} {model_text}{suffix}".strip()


def _append_product(entities: MarketingEntities, product: str) -> None:
    key = _compact_key(product)
    existing = {_compact_key(item) for item in entities.products}
    if key and key not in existing:
        entities.products.append(product)


def _is_exclusion_context(text: str) -> bool:
    lower = text.lower()
    return any(
        term in lower
        for term in (
            "exclude",
            "excludes",
            "not available",
            "optional features shown",
            "trademarks",
        )
    )


def _is_vehicle_offer_context(text: str) -> bool:
    lower = text.lower()
    return any(
        term in lower
        for term in (
            "lease for",
            "purchase",
            "cash allowance",
            "due at signing",
            "financing",
            "$",
            "/mo",
            "per month",
            "select",
        )
    )


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


def _price_key(price: PriceEntity) -> str:
    if price.amount is not None:
        return f"{_currency_symbol(price.currency)}:{price.amount:.2f}"
    return _compact_key(price.text)


def _normalize_price_entity(price: PriceEntity) -> PriceEntity:
    if price.amount is None:
        return price
    currency = _currency_symbol(price.currency)
    text = _format_price(currency, price.amount)
    return price.model_copy(update={"currency": currency, "text": text})


def _currency_symbol(currency: str | None) -> str:
    normalized = (currency or "$").strip().upper()
    if normalized in {"USD", "US$", "$"}:
        return "$"
    return currency or "$"


def _format_price(currency: str | None, amount: float) -> str:
    amount_text = (
        f"{int(amount):,}"
        if float(amount).is_integer()
        else f"{amount:,.2f}".rstrip("0").rstrip(".")
    )
    return f"{_currency_symbol(currency)}{amount_text}"


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


def _compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _merge_strings(left: list[str], right: list[str]) -> list[str]:
    merged = list(left)
    for item in right:
        if item and item not in merged:
            merged.append(item)
    return merged


def _merge_products(left: list[str], right: list[str]) -> list[str]:
    merged = list(left)
    for item in right:
        if not item:
            continue
        if any(_compact_key(item) == _compact_key(existing) for existing in merged):
            continue
        if any(_is_weaker_product_variant(item, existing) for existing in merged):
            continue
        merged = [existing for existing in merged if not _is_weaker_product_variant(existing, item)]
        merged.append(item)
    return merged


def _is_weaker_product_variant(candidate: str, existing: str) -> bool:
    candidate_tokens = _product_tokens(candidate)
    existing_tokens = _product_tokens(existing)
    if not candidate_tokens or not existing_tokens:
        return False
    if not {"wrangler", "grand", "cherokee", "gladiator", "pacifica"} & candidate_tokens:
        return False
    return candidate_tokens < existing_tokens


def _is_specific_vehicle_product(value: str) -> bool:
    tokens = _product_tokens(value)
    return bool({"wrangler", "grand", "cherokee", "gladiator", "pacifica"} & tokens)


def _is_generic_vehicle_make_product(
    value: str,
    brand_key: str,
    has_specific_vehicle: bool,
) -> bool:
    key = _compact_key(value)
    if key not in _GENERIC_VEHICLE_MAKE_KEYS:
        return False
    return has_specific_vehicle or (brand_key and key in brand_key)


def _product_tokens(value: str) -> set[str]:
    normalized = value.lower().replace("4-door", "4door").replace("4x4", "4x4")
    return set(re.findall(r"[a-z0-9]+", normalized))


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


def _merge_campaign_signals(left: CampaignSignals, right: CampaignSignals) -> CampaignSignals:
    for field in (
        "slogan",
        "recurring_offer",
        "product_model",
        "sku",
        "creative_variant",
        "campaign_theme",
    ):
        if getattr(left, field) is None:
            setattr(left, field, getattr(right, field))
    existing = {(item.time_ms, item.frame_index, item.source, item.text) for item in left.evidence}
    for item in right.evidence:
        key = (item.time_ms, item.frame_index, item.source, item.text)
        if key not in existing:
            left.evidence.append(item)
            existing.add(key)
    return left


def _max_density(left: str, right: str) -> str:
    return left if _DENSITY_RANK[left] >= _DENSITY_RANK[right] else right


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
