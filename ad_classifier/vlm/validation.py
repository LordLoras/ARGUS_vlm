from __future__ import annotations

import re

from ad_classifier.models.common import EvidenceItem
from ad_classifier.vlm.models import (
    VLMMarketingEntities,
    VLMVerificationResult,
)

_MIN_PRICE = 1.0
_MAX_PRICE = 1_000_000.0
_MAX_OFFER_LEN = 120


def validate_vlm_output(
    result: VLMVerificationResult,
    evidence_texts: list[str] | None = None,
) -> VLMVerificationResult:
    evidence_blob = " ".join(evidence_texts).lower() if evidence_texts else ""
    me = result.marketing_entities

    me.prices = [p for p in me.prices if _valid_price(p.amount)]
    me.offers = [o for o in me.offers if _valid_offer(o.value)]
    if me.brand and me.brand.name:
        me.brand.name = _clean_brand(me.brand.name)
    me.products = [p for p in me.products if len(p.strip()) >= 2]

    result.evidence = [e for e in result.evidence if len(e.text.strip()) >= 3]

    return result


def _valid_price(amount: float) -> bool:
    if amount is None:
        return False
    return _MIN_PRICE <= amount <= _MAX_PRICE


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
