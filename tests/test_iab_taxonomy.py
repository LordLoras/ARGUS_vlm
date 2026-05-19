from __future__ import annotations

from ad_classifier.iab_taxonomy import infer_iab_category, load_iab_taxonomy, normalize_iab_category
from ad_classifier.models.iab import IABAlternativeCategory, IABCategory


def test_load_iab_taxonomy_builds_full_paths():
    taxonomy = load_iab_taxonomy()

    entry = taxonomy["1554"]

    assert entry.parent_id == "1553"
    assert entry.selected_depth == 3
    assert entry.selected_category == "New Vehicle Ownership"
    assert entry.full_path == "Vehicles > Automotive Ownership > New Vehicle Ownership"


def test_normalize_iab_category_canonicalizes_selected_row_and_alternatives():
    result = normalize_iab_category(
        IABCategory(
            iab_unique_id="1554",
            tier_1="Vehicles",
            selected_depth=1,
            selected_category="Vehicles",
            full_path="Vehicles",
            confidence=0.82,
            alternative_categories=[
                IABAlternativeCategory(
                    iab_unique_id="1552",
                    full_path="Vehicles > Automotive Leasing",
                    use_when="The ad says lease.",
                )
            ],
        )
    )

    assert result is not None
    assert result.confidence == "high"
    assert result.iab_parent_id == "1553"
    assert result.tier_2 == "Automotive Ownership"
    assert result.alternative_categories[0].iab_unique_id == "1552"


def test_infer_iab_category_corrects_broad_cosmetics_to_skin_care():
    result = infer_iab_category(
        IABCategory(
            iab_unique_id="1138",
            selected_depth=2,
            selected_category="Cosmetics",
            full_path="Consumer Packaged Goods > Cosmetics",
            confidence="high",
        ),
        primary_category="beauty_personal_care",
        subcategory="skincare",
        products=["Absolue Longevity MD Reset The Cream"],
        evidence_texts=["NOW IN SKINCARE", "Reverse skin visible aging signs"],
    )

    assert result is not None
    assert result.iab_unique_id == "1244"
    assert result.full_path == "Consumer Packaged Goods > Skin Care"
