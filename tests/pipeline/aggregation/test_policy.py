from __future__ import annotations

from ad_classifier.pipeline.aggregation.models import AggregationConfig
from ad_classifier.pipeline.aggregation.policy import aggregate
from ad_classifier.pipeline.rules.models import RuleTrigger
from ad_classifier.vlm.models import VLMVerificationResult


def _vlm(
    *,
    decision="allow",
    confidence=0.85,
    primary_category="retail_ecommerce",
    risk_labels=None,
) -> VLMVerificationResult:
    return VLMVerificationResult(
        primary_category=primary_category,
        risk_labels=risk_labels or [],
        confidence=confidence,
        decision=decision,
        needs_human_review=False,
        summary="test",
    )


def _rule(risk_label: str = "deceptive_urgency") -> RuleTrigger:
    return RuleTrigger(
        rule_id="test_rule",
        severity="high",
        risk_label=risk_label,
        evidence_text="limited time only",
        source="ocr",
        time_ms=500,
    )


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


def test_clean_ad_allows():
    result = aggregate("ad_1", _vlm(decision="allow", confidence=0.85), [])
    assert result.decision == "allow"
    assert result.needs_human_review is False


def test_low_confidence_routes_to_review():
    result = aggregate("ad_1", _vlm(decision="allow", confidence=0.50), [])
    assert result.decision == "review"
    assert result.needs_human_review is True


def test_vlm_flag_with_high_confidence_flags():
    result = aggregate("ad_1", _vlm(decision="flag", confidence=0.90), [])
    assert result.decision == "flag"
    assert result.needs_human_review is True


def test_vlm_flag_low_confidence_still_flags_needs_review():
    result = aggregate("ad_1", _vlm(decision="flag", confidence=0.50), [])
    # Low confidence flag: rule engine has no triggers, VLM says flag but below threshold
    # → review
    assert result.decision == "review"


def test_rule_trigger_escalates_to_review():
    result = aggregate("ad_1", _vlm(decision="allow", confidence=0.85), [_rule()])
    assert result.decision in ("review", "flag")
    assert result.needs_human_review is True


def test_rule_risk_labels_merged():
    result = aggregate(
        "ad_1",
        _vlm(decision="allow", confidence=0.85, risk_labels=["price_manipulation"]),
        [_rule("deceptive_urgency")],
    )
    assert "price_manipulation" in result.risk_labels
    assert "deceptive_urgency" in result.risk_labels


def test_sensitive_category_lowers_threshold():
    # health_wellness is sensitive → threshold = 0.50 (sensitive_review_threshold)
    # confidence=0.60 > 0.50 → allow
    cfg = AggregationConfig(sensitive_review_threshold=0.50)
    result = aggregate(
        "ad_1",
        _vlm(decision="allow", confidence=0.60, primary_category="health_wellness"),
        [],
        config=cfg,
    )
    assert result.decision == "allow"


def test_sensitive_category_below_threshold_reviews():
    cfg = AggregationConfig(sensitive_review_threshold=0.70)
    result = aggregate(
        "ad_1",
        _vlm(decision="allow", confidence=0.60, primary_category="health_wellness"),
        [],
        config=cfg,
    )
    assert result.decision == "review"


# ---------------------------------------------------------------------------
# Marketing entity mapping
# ---------------------------------------------------------------------------


def test_brand_name_in_marketing_entities():
    vlm = _vlm()
    vlm.marketing_entities.brand.name = "Nike"
    result = aggregate("ad_1", vlm, [])
    assert result.marketing_entities.brand.name == "Nike"


def test_products_mapped():
    vlm = _vlm()
    vlm.marketing_entities.products = ["Product A", "Product B"]
    result = aggregate("ad_1", vlm, [])
    assert result.marketing_entities.products == ["Product A", "Product B"]


def test_zero_amount_prices_are_not_mapped():
    from ad_classifier.vlm.models import VLMPrice

    vlm = _vlm()
    vlm.marketing_entities.prices = [VLMPrice(amount=0), VLMPrice(amount=95, currency="$")]
    result = aggregate("ad_1", vlm, [])

    assert [price.amount for price in result.marketing_entities.prices] == [95]


def test_tracking_fields_mapped():
    from ad_classifier.vlm.models import (
        VLMLogoEvidence,
        VLMPromoCode,
        VLMWebsite,
    )

    vlm = _vlm()
    vlm.marketing_entities.contact_points.websites = [
        VLMWebsite(
            url="https://example.com/deal",
            domain="example.com",
            evidence=[VLMLogoEvidence(time_ms=1000, frame_index=2, text="example.com")],
        )
    ]
    vlm.marketing_entities.offer_terms.promo_codes = [VLMPromoCode(code="SAVE20")]
    vlm.marketing_entities.creative_attributes.end_card = True
    result = aggregate("ad_1", vlm, [])

    assert result.marketing_entities.primary_website_domain == "example.com"
    assert result.marketing_entities.offer_terms.promo_codes[0].code == "SAVE20"
    assert result.marketing_entities.creative_attributes.end_card is True


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_vlm_evidence_included():
    from ad_classifier.vlm.models import VLMEvidence

    vlm = _vlm()
    vlm.evidence = [
        VLMEvidence(
            time_ms=1000, frame_index=2, source="vlm", text="sale 50% off", reason="visible text"
        )
    ]
    result = aggregate("ad_1", vlm, [])
    assert any(e.source == "vlm" for e in result.evidence)


def test_rule_evidence_included():
    result = aggregate("ad_1", _vlm(), [_rule()])
    assert any(e.source == "rule" for e in result.evidence)
