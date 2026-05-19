from __future__ import annotations

from ad_classifier.iab_content_taxonomy import (
    load_iab_content_taxonomy,
    normalize_iab_content_categories,
)
from ad_classifier.models.iab import IABContentCategory


def test_load_iab_content_taxonomy_builds_suv_path():
    taxonomy = load_iab_content_taxonomy()

    entry = taxonomy["6"]

    assert entry.parent_id == "2"
    assert entry.selected_depth == 3
    assert entry.selected_category == "SUV"
    assert entry.full_path == "Automotive > Auto Body Styles > SUV"


def test_normalize_iab_content_categories_canonicalizes_and_dedupes():
    result = normalize_iab_content_categories(
        [
            IABContentCategory(
                iab_unique_id="6",
                iab_parent_id="wrong",
                tier_1="Automotive",
                selected_depth=1,
                selected_category="Automotive",
                full_path="Automotive",
                confidence="high",
                reason="SUV appears in the ad",
            ),
            {
                "iab_unique_id": "bad",
                "selected_depth": 1,
                "selected_category": "SUV",
                "full_path": "Automotive > Auto Body Styles > SUV",
                "confidence": 0.8,
            },
        ]
    )

    assert len(result) == 1
    assert result[0].iab_unique_id == "6"
    assert result[0].iab_parent_id == "2"
    assert result[0].tier_3 == "SUV"
    assert result[0].confidence == "high"
    assert [node.iab_unique_id for node in result[0].parent_categories] == ["1", "2"]
