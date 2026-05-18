from __future__ import annotations

from ad_classifier.models.iab import IABCategory
from ad_classifier.pipeline.aggregation.policy import aggregate
from ad_classifier.pipeline.rules.models import RuleTrigger
from ad_classifier.vlm.models import VLMVerificationResult


def _vlm(
    *,
    confidence=0.85,
    primary_category="retail",
) -> VLMVerificationResult:
    return VLMVerificationResult(
        primary_category=primary_category,
        confidence=confidence,
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
# Marketing entity mapping
# ---------------------------------------------------------------------------


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


def test_iab_category_is_canonicalized_from_vlm_id():
    vlm = _vlm(primary_category="automotive")
    vlm.iab_category = IABCategory(
        iab_unique_id="1554",
        iab_parent_id="wrong",
        tier_1="Vehicles",
        selected_depth=1,
        selected_category="Vehicles",
        full_path="Vehicles",
        confidence="high",
    )

    result = aggregate("ad_1", vlm, [])

    assert result.iab_category is not None
    assert result.iab_category.iab_parent_id == "1553"
    assert result.iab_category.selected_depth == 3
    assert (
        result.iab_category.full_path == "Vehicles > Automotive Ownership > New Vehicle Ownership"
    )
    assert [node.iab_unique_id for node in result.iab_category.parent_categories] == [
        "1551",
        "1553",
    ]


def test_zero_amount_prices_are_not_mapped():
    from ad_classifier.vlm.models import VLMPrice

    vlm = _vlm()
    vlm.marketing_entities.prices = [VLMPrice(amount=0), VLMPrice(amount=95, currency="$")]
    result = aggregate("ad_1", vlm, [])

    assert [price.amount for price in result.marketing_entities.prices] == [95]


def test_usd_prices_render_as_dollar_amounts():
    from ad_classifier.vlm.models import VLMPrice

    vlm = _vlm()
    vlm.marketing_entities.prices = [VLMPrice(amount=400, currency="USD", time_ms=1000)]
    result = aggregate("ad_1", vlm, [])

    assert result.marketing_entities.prices[0].text == "$400"
    assert result.marketing_entities.prices[0].currency == "$"


def test_large_prices_render_with_grouping():
    from ad_classifier.vlm.models import VLMPrice

    vlm = _vlm()
    vlm.marketing_entities.prices = [VLMPrice(amount=4500, currency="USD", time_ms=1000)]
    result = aggregate("ad_1", vlm, [])

    assert result.marketing_entities.prices[0].text == "$4,500"


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


def test_duplicate_rule_evidence_collapses_adjacent_ocr_variants():
    rules = [
        RuleTrigger(
            rule_id="financial_apr",
            severity="low",
            evidence_text=(
                "Offers exclude 4xe models.0% APR financing for 60 months equals$16.67 "
                "per month per$1,000 financed"
            ),
            source="ocr",
            time_ms=15000,
            frame_index=30,
        ),
        RuleTrigger(
            rule_id="financial_apr",
            severity="low",
            evidence_text=(
                "Offers exclude 4xe models. 0% APR financing for 60 months equals $16.67 "
                "per month per $1,000 financed"
            ),
            source="ocr",
            time_ms=16000,
            frame_index=32,
        ),
    ]

    result = aggregate("ad_1", _vlm(), rules)
    rule_evidence = [item for item in result.evidence if item.source == "rule"]

    assert len(rule_evidence) == 1
    assert "equals $16.67" in rule_evidence[0].text
    assert "per $1,000" in rule_evidence[0].text


def test_rule_evidence_fuzzy_dedup_collapses_near_identical_garbled_text():
    rules = [
        RuleTrigger(
            rule_id="financial_apr",
            category="automotive",
            severity="low",
            source="ocr",
            time_ms=12000,
            frame_index=24,
            evidence_text="0%APR financirg for36 months equals $27.78 per month per$1,000 financed",
        ),
        RuleTrigger(
            rule_id="financial_apr",
            category="automotive",
            severity="low",
            source="ocr",
            time_ms=13000,
            frame_index=26,
            evidence_text="0% APR financing for 36 months equals$27.78 per month per $1,000 financed",
        ),
        RuleTrigger(
            rule_id="financial_apr",
            category="automotive",
            severity="low",
            source="ocr",
            time_ms=13500,
            frame_index=27,
            evidence_text="0% APR financing for36 months eqals$27.78 permonth per$1,000 fnanced",
        ),
        RuleTrigger(
            rule_id="financial_apr",
            category="automotive",
            severity="low",
            source="ocr",
            time_ms=16000,
            frame_index=32,
            evidence_text=(
                "purchase Excudes leases. Offer not available in DC. "
                "Only those PA residents who finance at 0% APR"
            ),
        ),
        RuleTrigger(
            rule_id="financial_apr",
            category="automotive",
            severity="low",
            source="ocr",
            time_ms=17000,
            frame_index=34,
            evidence_text=(
                "purchase Excudes leases. Offer not availabie in DC. "
                "Only those PA residents who finance at 0% APR"
            ),
        ),
    ]

    result = aggregate("ad_dedup", _vlm(), rules)
    rule_evidence = [item for item in result.evidence if item.source == "rule"]

    assert len(rule_evidence) == 2
    texts = [e.text for e in rule_evidence]
    assert any("27.78" in t for t in texts)
    assert any("purchase" in t.lower() for t in texts)
