from __future__ import annotations

from ad_classifier.vlm.prompt import (
    get_prompt_version,
    prompt_template_options,
    render_verifier_prompt,
    resolve_prompt_profile,
)


def test_renders_without_error():
    prompt = render_verifier_prompt()
    assert isinstance(prompt, str)
    assert len(prompt) > 100


def test_placeholders_replaced():
    prompt = render_verifier_prompt()
    assert "{ALLOWED_CATEGORIES}" not in prompt
    assert "{ALLOWED_RISK_LABELS}" not in prompt
    assert "{SENSITIVE_CATEGORIES}" not in prompt
    assert "{IAB_PRODUCT_TAXONOMY}" not in prompt
    assert "{IAB_CONTENT_TAXONOMY}" not in prompt


def test_contains_known_category():
    prompt = render_verifier_prompt()
    assert "automotive" in prompt
    assert "gambling" in prompt


def test_contains_iab_product_taxonomy():
    prompt = render_verifier_prompt()
    assert "Allowed IAB product taxonomy entries" in prompt
    assert (
        "1554 | parent=1553 | depth=3 | Vehicles > Automotive Ownership > New Vehicle Ownership"
        in prompt
    )


def test_contains_iab_content_taxonomy():
    prompt = render_verifier_prompt()
    assert "Allowed IAB content taxonomy entries" in prompt
    assert "6 | parent=2 | depth=3 | Automotive > Auto Body Styles > SUV" in prompt
    assert "559 | parent=553 | depth=3 | Style & Fashion > Beauty > Skin Care" in prompt


def test_sensitive_categories_included():
    prompt = render_verifier_prompt()
    assert "healthcare_pharma" in prompt
    assert "banking_lending" in prompt


def test_prompt_is_categorization_only():
    prompt = render_verifier_prompt()
    assert "CATEGORIZATION ONLY" in prompt
    assert "do not output review or decision fields" in prompt
    assert "needs_human_review" not in prompt


def test_prompt_restricts_campaign_suggestion_names():
    prompt = render_verifier_prompt()
    assert "Campaign suggestions" in prompt
    assert "Do NOT invent generic campaign buckets" in prompt


def test_prompt_extracts_partnership_badges_and_disclosures():
    prompt = render_verifier_prompt()
    assert "America 250" in prompt
    assert "partnership marks" in prompt
    assert "AI-generated performers" in prompt


def test_prompt_guides_beauty_content_categories():
    prompt = render_verifier_prompt()
    assert "For beauty/personal-care ads" in prompt
    assert "Skin Care" in prompt
    assert "use Skin Care instead of broad Cosmetics" in prompt


def test_prompt_rejects_incidental_music_and_animation_content_labels():
    prompt = render_verifier_prompt()
    assert "Do not output Music merely because the ad has background music" in prompt
    assert "Do not output Animation & Anime merely because the ad is a TV/program spot" in prompt
    assert "omit it" in prompt


def test_prompt_falls_back_when_knowledge_taxonomy_is_empty():
    class EmptyKnowledge:
        def render_product_taxonomy_for_prompt(self) -> str:
            return "- no IAB product taxonomy loaded"

        def render_content_taxonomy_for_prompt(self) -> str:
            return "- no IAB content taxonomy loaded"

    prompt = render_verifier_prompt(knowledge_manager=EmptyKnowledge())

    assert "1554 | parent=1553 | depth=3 | Vehicles > Automotive Ownership" in prompt
    assert "6 | parent=2 | depth=3 | Automotive > Auto Body Styles > SUV" in prompt


def test_frontier_strict_prompt_renders_compact_rules():
    prompt = render_verifier_prompt(prompt_profile="frontier_strict")

    assert "frontier-strict mode" in prompt
    assert "Do not promote fine-print-only fees" in prompt
    assert "{IAB_PRODUCT_TAXONOMY}" not in prompt
    assert "1554 | parent=1553 | depth=3 | Vehicles > Automotive Ownership" in prompt


def test_prompt_profile_auto_resolution():
    assert resolve_prompt_profile("auto", mode="frontier") == "frontier_strict"
    assert resolve_prompt_profile("auto", mode="local") == "standard"
    assert get_prompt_version("frontier_strict").startswith("verifier-frontier-strict-")


def test_prompt_override_still_gets_runtime_taxonomy():
    prompt = render_verifier_prompt(
        prompt_profile="standard",
        prompt_text="# version: verifier-custom\nCategories:\n{ALLOWED_CATEGORIES}",
    )

    assert "automotive" in prompt
    assert "{ALLOWED_CATEGORIES}" not in prompt


def test_prompt_template_options_include_reset_defaults():
    options = prompt_template_options()
    profiles = {item["profile"] for item in options}

    assert profiles == {"standard", "frontier_strict"}
    assert all(item["default_text"] for item in options)
    assert all(item["version"].startswith("verifier-") for item in options)


def test_custom_prompt_version_is_marked_custom():
    assert (
        get_prompt_version("standard", prompt_text="# version: verifier-custom\nBody")
        == "custom:verifier-custom"
    )
