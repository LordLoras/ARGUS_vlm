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
    assert "{SUBCATEGORY_HINTS}" not in prompt


def test_contains_known_category():
    prompt = render_verifier_prompt()
    assert "retail_ecommerce" in prompt
    assert "gambling" in prompt


def test_contains_known_risk_label():
    prompt = render_verifier_prompt()
    assert "deceptive_urgency" in prompt


def test_sensitive_categories_included():
    prompt = render_verifier_prompt()
    assert "health_wellness" in prompt
    assert "crypto_investment" in prompt
