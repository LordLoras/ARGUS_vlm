from __future__ import annotations

import pytest
from pydantic import ValidationError

from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import BrandEntity, MarketingEntities


def test_marketing_entities_projection_text():
    entities = MarketingEntities(
        brand=BrandEntity(name="Example Brand", confidence=0.91),
        products=["Widget", "Widget Pro"],
    )

    assert entities.brand.name == "Example Brand"
    assert entities.products_text == "Widget, Widget Pro"


def test_evidence_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        EvidenceItem(
            time_ms=0,
            source="ocr",
            text="SALE",
            confidence=1.5,
        )
