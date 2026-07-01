from __future__ import annotations

from ad_classifier.intelligence_crawler.meta_ad_library_probe import (
    TOYOTA_META_AD_LIBRARY_URL,
    _clean_image_sources,
    _clean_links,
    _parse_card_text,
    _safe_filename,
)


def test_toyota_meta_probe_url_is_page_search_for_us_active_ads() -> None:
    assert "facebook.com/ads/library/" in TOYOTA_META_AD_LIBRARY_URL
    assert "active_status=active" in TOYOTA_META_AD_LIBRARY_URL
    assert "country=US" in TOYOTA_META_AD_LIBRARY_URL
    assert "view_all_page_id=197052454200" in TOYOTA_META_AD_LIBRARY_URL


def test_parse_card_text_extracts_library_id_status_date_and_platforms() -> None:
    parsed = _parse_card_text(
        """
        Active
        Library ID: 1234567890
        Started running on Jun 25, 2026
        Platforms Facebook Instagram Messenger
        Toyota Summer Sales Event
        """
    )

    assert parsed == {
        "library_id": "1234567890",
        "status": "active",
        "started_running": "Jun 25, 2026",
        "platforms": ["Facebook", "Instagram", "Messenger"],
        "creative_variant_count": None,
        "has_multiple_versions": False,
    }


def test_parse_card_text_extracts_multiple_version_count() -> None:
    parsed = _parse_card_text(
        """
        Toyota
        Active
        Library ID: 2900281893668121
        Started running on Jun 25, 2026
        Platforms
        This ad has multiple versions
        5 ads use this creative and text
        Open Dropdown
        """
    )

    assert parsed["library_id"] == "2900281893668121"
    assert parsed["creative_variant_count"] == 5
    assert parsed["has_multiple_versions"] is True


def test_parse_card_text_handles_missing_optional_fields() -> None:
    parsed = _parse_card_text("Library ID 987 Some Toyota creative text")

    assert parsed["library_id"] == "987"
    assert parsed["status"] is None
    assert parsed["started_running"] is None
    assert parsed["platforms"] == []
    assert parsed["creative_variant_count"] is None
    assert parsed["has_multiple_versions"] is False


def test_clean_helpers_dedupe_and_limit_values() -> None:
    links = _clean_links(
        [
            {"text": " Toyota ", "href": "https://toyota.com"},
            {"text": "Toyota", "href": "https://toyota.com"},
            {"text": "", "href": ""},
            {"text": "Learn more", "href": ""},
        ]
    )
    images = _clean_image_sources(["https://img/1", "https://img/1", "", None, "https://img/2"])

    assert links == [
        {"text": "Toyota", "href": "https://toyota.com"},
        {"text": "Learn more", "href": ""},
    ]
    assert images == ["https://img/1", "https://img/2"]


def test_clean_links_unwraps_fb_redirect_and_drops_framework_junk() -> None:
    links = _clean_links(
        [
            {
                "text": "TOYOTA.COM/RAV4 Learn More",
                "href": (
                    "https://l.facebook.com/l.php?u="
                    "https%3A%2F%2Fad.doubleclick.net%2Fddm%2Fclk%2F123"
                ),
            },
            {"text": "amp runtime", "href": "https://cdn.ampproject.org/amp4ads-host-v0.js"},
            {"text": "Direct", "href": "https://www.toyota.com/rav4"},
        ]
    )
    # FB wrapper unwrapped to the real click URL
    assert {
        "text": "TOYOTA.COM/RAV4 Learn More",
        "href": "https://ad.doubleclick.net/ddm/clk/123",
    } in links
    # framework script dropped to text-only (junk href removed)
    assert {"text": "amp runtime", "href": ""} in links
    # a plain landing page is untouched
    assert {"text": "Direct", "href": "https://www.toyota.com/rav4"} in links


def test_safe_filename_strips_problem_characters() -> None:
    assert _safe_filename(" 123/456:789 ") == "123_456_789"
