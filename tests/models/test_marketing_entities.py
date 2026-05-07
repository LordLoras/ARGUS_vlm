from __future__ import annotations

import pytest
from pydantic import ValidationError

from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import (
    BrandEntity,
    ContactPoints,
    LandingPageEntity,
    MarketingEntities,
    PhoneNumberEntity,
    WebsiteEntity,
)


def test_marketing_entities_projection_text():
    entities = MarketingEntities(
        brand=BrandEntity(name="Example Brand", confidence=0.91),
        products=["Widget", "Widget Pro"],
    )

    assert entities.brand.name == "Example Brand"
    assert entities.products_text == "Widget, Widget Pro"


def test_marketing_entities_tracking_projections():
    entities = MarketingEntities(
        contact_points=ContactPoints(
            websites=[WebsiteEntity(url="https://example.com", domain="example.com")],
            phone_numbers=[PhoneNumberEntity(raw="555-123-4567", normalized="+15551234567")],
        ),
        landing_page=LandingPageEntity(domain="landing.example"),
    )

    assert entities.primary_website_domain == "example.com"
    assert entities.primary_phone_number == "+15551234567"


def test_evidence_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        EvidenceItem(
            time_ms=0,
            source="ocr",
            text="SALE",
            confidence=1.5,
        )
