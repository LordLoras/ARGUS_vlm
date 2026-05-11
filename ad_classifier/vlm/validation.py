from __future__ import annotations

import re
from pathlib import Path

import yaml

from ad_classifier.models.common import EvidenceItem
from ad_classifier.vlm.models import (
    VLMMarketingEntities,
    VLMVerificationResult,
)

_MIN_PRICE = 1.0
_MAX_PRICE = 1_000_000.0
_MAX_OFFER_LEN = 120
_TAXONOMY_PATH = Path(__file__).parent.parent.parent / "taxonomy.yaml"


def _load_category_ids() -> set[str]:
    try:
        data = yaml.safe_load(_TAXONOMY_PATH.read_text(encoding="utf-8")) or {}
        return {c["id"] for c in data.get("categories", []) if "id" in c}
    except Exception:
        return set()


def validate_vlm_output(
    result: VLMVerificationResult,
    evidence_texts: list[str] | None = None,
) -> VLMVerificationResult:
    evidence_blob = " ".join(evidence_texts).lower() if evidence_texts else ""
    me = result.marketing_entities

    allowed_categories = _load_category_ids()
    if allowed_categories and result.primary_category not in allowed_categories:
        result.primary_category = "other"
        result.confidence = min(result.confidence, 0.3)

    me.prices = [p for p in me.prices if _valid_price(p.amount)]
    me.prices = _filter_non_vehicle_prices(me.prices, evidence_blob)
    me.offers = [o for o in me.offers if _valid_offer(o.value)]
    if me.brand and me.brand.name:
        cleaned = _clean_brand(me.brand.name)
        if cleaned and evidence_blob and not _brand_in_evidence(cleaned, evidence_blob):
            pass
        me.brand.name = cleaned
    me.products = [p for p in me.products if len(p.strip()) >= 2]

    if evidence_blob:
        me.products = [p for p in me.products if _product_in_evidence(p, evidence_blob)]

    result.evidence = [e for e in result.evidence if len(e.text.strip()) >= 3]

    return result


def _brand_in_evidence(brand: str, evidence_blob: str) -> bool:
    brand_lower = brand.lower()
    words = [w for w in brand_lower.split() if len(w) > 2]
    if not words:
        return True
    return any(w in evidence_blob for w in words)


def _product_in_evidence(product: str, evidence_blob: str) -> bool:
    product_lower = product.lower()
    tokens = [t for t in product_lower.split() if len(t) > 2 and not t.isdigit()]
    if not tokens:
        return True
    return any(t in evidence_blob for t in tokens)


def _valid_price(amount: float) -> bool:
    if amount is None:
        return False
    return _MIN_PRICE <= amount <= _MAX_PRICE


_NON_PRICE_CONTEXT = re.compile(
    r"(?:cash\s*allowance|bonus\s*cash|per\s*\$[\d,]+|per\s*month|per\s*\$1[, ]*000"
    r"|down\s*payment|dealer\s*fee|document|filing\s*fee|doc\s*fee"
    r"|monthly\s*payment|per\s*month|trade.in\s*assist|loyalty\s*cash)",
    re.IGNORECASE,
)


def _filter_non_vehicle_prices(prices: list, evidence_blob: str) -> list:
    if not evidence_blob:
        return prices
    filtered = []
    for p in prices:
        for ev in p.evidence if hasattr(p, "evidence") else []:
            ctx = (ev.text or "").lower()
            if _NON_PRICE_CONTEXT.search(ctx):
                break
        else:
            filtered.append(p)
            continue
    return filtered


def _valid_offer(text: str) -> bool:
    if not text or len(text) < 3:
        return False
    if len(text) > _MAX_OFFER_LEN:
        return False
    words = text.split()
    if not words:
        return False
    alpha = sum(c.isalpha() for c in text)
    if alpha == 0:
        return False
    return True


def _clean_brand(name: str) -> str:
    name = re.sub(r"[®™©]", "", name).strip()
    if len(name) > 60:
        name = name[:60].rsplit(" ", 1)[0]
    return name
