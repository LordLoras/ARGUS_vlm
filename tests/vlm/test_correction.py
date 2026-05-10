from __future__ import annotations

import json

from ad_classifier.vlm.correction import _apply_corrections
from ad_classifier.vlm.models import (
    VLMMarketingEntities,
    VLMBrand,
    VLMVerificationResult,
)


def test_apply_corrections_fixes_category():
    result = VLMVerificationResult(
        primary_category="food_beverage",
        confidence=0.9,
        marketing_entities=VLMMarketingEntities(
            brand=VLMBrand(name="Jeep"),
            products=["Grand Cherokee"],
        ),
    )
    raw = json.dumps({"corrections": {"primary_category": "automotive"}})
    corrected = _apply_corrections(result, raw)
    assert corrected.primary_category == "automotive"
    assert corrected.marketing_entities.products == ["Grand Cherokee"]


def test_apply_corrections_no_corrections():
    result = VLMVerificationResult(
        primary_category="automotive",
        confidence=0.9,
    )
    raw = json.dumps({"corrections": {}})
    corrected = _apply_corrections(result, raw)
    assert corrected.primary_category == "automotive"


def test_apply_corrections_bad_json_returns_unchanged():
    result = VLMVerificationResult(
        primary_category="automotive",
        confidence=0.9,
    )
    corrected = _apply_corrections(result, "not json")
    assert corrected.primary_category == "automotive"


def test_apply_corrections_fixes_products():
    result = VLMVerificationResult(
        primary_category="automotive",
        confidence=0.9,
        marketing_entities=VLMMarketingEntities(
            products=["iPhone Pro Max"],
        ),
    )
    raw = json.dumps({"corrections": {"products": ["Grand Cherokee", "Wrangler"]}})
    corrected = _apply_corrections(result, raw)
    assert corrected.marketing_entities.products == ["Grand Cherokee", "Wrangler"]
