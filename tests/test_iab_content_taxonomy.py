from __future__ import annotations

from ad_classifier.iab_content_taxonomy import (
    iab_content_category_from_id,
    infer_iab_content_categories,
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


def test_iab_content_category_from_id_builds_canonical_node():
    category = iab_content_category_from_id("559", reason="matched skincare")

    assert category is not None
    assert category.iab_unique_id == "559"
    assert category.iab_parent_id == "553"
    assert category.full_path == "Style & Fashion > Beauty > Skin Care"
    assert [node.iab_unique_id for node in category.parent_categories] == ["552", "553"]


def test_infer_iab_content_categories_adds_skin_care_from_evidence():
    result = infer_iab_content_categories(
        primary_category="beauty_personal_care",
        subcategory="skincare",
        products=["Absolue Longevity MD Reset The Cream"],
        product_iab_path="Consumer Packaged Goods > Cosmetics",
        evidence_texts=["NOW IN SKINCARE", "Reverse skin visible aging signs and fine lines"],
    )

    assert [category.iab_unique_id for category in result] == ["559"]
    assert result[0].full_path == "Style & Fashion > Beauty > Skin Care"
    assert "skincare" in result[0].reason


def test_infer_iab_content_categories_does_not_duplicate_existing():
    existing = iab_content_category_from_id("559", confidence="high", reason="vlm selected")
    result = infer_iab_content_categories(
        existing=[existing],
        primary_category="beauty_personal_care",
        subcategory="skincare",
        evidence_texts=["skin care serum"],
    )

    assert [category.iab_unique_id for category in result] == ["559"]
    assert result[0].confidence == "high"


def test_infer_iab_content_categories_drops_negated_music_and_animation():
    sports = iab_content_category_from_id(
        "483",
        confidence="high",
        reason="hockey and playoff action are visible and spoken",
    )
    music = iab_content_category_from_id(
        "338",
        confidence="medium",
        reason="Music is not the focus and only accompanies the spot. Excluded.",
    )
    animation = iab_content_category_from_id(
        "641",
        confidence="high",
        reason="The ad is a spot for a weekly television program.",
    )

    result = infer_iab_content_categories(
        existing=[sports, music, animation],
        primary_category="entertainment_media",
        subcategory="Sports Broadcasting",
        products=["Hockey in the Desert Weekly", "Vegas+"],
        product_iab_path="Media > Live Television",
        evidence_texts=["Golden Knights hockey playoff action on FOX 5"],
    )

    assert [category.iab_unique_id for category in result] == ["483"]


def test_infer_iab_content_categories_keeps_music_when_directly_supported():
    music = iab_content_category_from_id(
        "338",
        confidence="high",
        reason="The ad promotes a live concert broadcast.",
    )

    result = infer_iab_content_categories(
        existing=[music],
        primary_category="entertainment_media",
        evidence_texts=["Tonight live concert music special with featured artists"],
    )

    assert [category.iab_unique_id for category in result] == ["338"]


def test_infer_iab_content_categories_drops_background_music_only_support():
    sports = iab_content_category_from_id("483", confidence="high", reason="hockey promo")
    music = iab_content_category_from_id("338", confidence="high", reason="music is heard")

    result = infer_iab_content_categories(
        existing=[sports, music],
        primary_category="entertainment_media",
        subcategory="Sports Broadcasting",
        products=["Hockey in the Desert Weekly"],
        product_iab_path="Media > Live Television",
        evidence_texts=["background music plays under Golden Knights playoff highlights"],
    )

    assert [category.iab_unique_id for category in result] == ["483"]


def test_infer_iab_content_categories_keeps_animation_when_directly_supported():
    animation = iab_content_category_from_id(
        "641",
        confidence="high",
        reason="The ad promotes an anime series.",
    )

    result = infer_iab_content_categories(
        existing=[animation],
        primary_category="entertainment_media",
        evidence_texts=["New anime series streaming tonight"],
    )

    assert [category.iab_unique_id for category in result] == ["641"]


def test_infer_iab_content_categories_drops_animated_graphics_only_support():
    sports = iab_content_category_from_id("483", confidence="high", reason="hockey promo")
    animation = iab_content_category_from_id(
        "641",
        confidence="high",
        reason="animated graphics appear in the spot",
    )

    result = infer_iab_content_categories(
        existing=[sports, animation],
        primary_category="entertainment_media",
        subcategory="Sports Broadcasting",
        products=["Hockey in the Desert Weekly"],
        product_iab_path="Media > Live Television",
        evidence_texts=["animated graphics transition into Golden Knights playoff highlights"],
    )

    assert [category.iab_unique_id for category in result] == ["483"]
