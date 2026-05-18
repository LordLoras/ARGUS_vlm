from __future__ import annotations

from ad_classifier.vlm.prompt import render_verifier_prompt


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
