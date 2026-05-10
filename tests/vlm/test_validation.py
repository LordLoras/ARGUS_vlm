from __future__ import annotations

from ad_classifier.vlm.models import (
    VLMMarketingEntities,
    VLMPrice,
    VLMOffer,
    VLMBrand,
    VLMEvidence,
    VLMVerificationResult,
)
from ad_classifier.vlm.validation import validate_vlm_output


def test_validate_removes_tiny_prices():
    result = VLMVerificationResult(
        primary_category="automotive",
        confidence=0.9,
        marketing_entities=VLMMarketingEntities(
            prices=[VLMPrice(amount=0.3, currency="$"), VLMPrice(amount=359.0, currency="$")],
        ),
    )
    validated = validate_vlm_output(result)
    assert len(validated.marketing_entities.prices) == 1
    assert validated.marketing_entities.prices[0].amount == 359.0


def test_validate_removes_huge_prices():
    result = VLMVerificationResult(
        primary_category="automotive",
        confidence=0.9,
        marketing_entities=VLMMarketingEntities(
            prices=[VLMPrice(amount=2_000_000.0, currency="$")],
        ),
    )
    validated = validate_vlm_output(result)
    assert len(validated.marketing_entities.prices) == 0


def test_validate_removes_long_offers():
    result = VLMVerificationResult(
        primary_category="automotive",
        confidence=0.9,
        marketing_entities=VLMMarketingEntities(
            offers=[
                VLMOffer(value="0% APR financing for 36 months"),
                VLMOffer(value="x" * 200),
            ],
        ),
    )
    validated = validate_vlm_output(result)
    assert len(validated.marketing_entities.offers) == 1


def test_validate_cleans_brand_symbols():
    result = VLMVerificationResult(
        primary_category="automotive",
        confidence=0.9,
        marketing_entities=VLMMarketingEntities(
            brand=VLMBrand(name="Jeep\u00ae"),
        ),
    )
    validated = validate_vlm_output(result)
    assert validated.marketing_entities.brand.name == "Jeep"


def test_validate_removes_empty_products():
    result = VLMVerificationResult(
        primary_category="other",
        confidence=0.8,
        marketing_entities=VLMMarketingEntities(
            products=["SUV", "", "  "],
        ),
    )
    validated = validate_vlm_output(result)
    assert validated.marketing_entities.products == ["SUV"]


def test_validate_removes_empty_evidence():
    result = VLMVerificationResult(
        primary_category="other",
        confidence=0.8,
        evidence=[
            VLMEvidence(text="0% APR financing"),
            VLMEvidence(text=""),
            VLMevidence := VLMEvidence(text="  "),
        ],
    )
    validated = validate_vlm_output(result)
    assert len(validated.evidence) == 1
