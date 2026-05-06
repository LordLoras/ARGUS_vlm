from __future__ import annotations

from ad_classifier.marketing.brand import brand_normalize


def test_none_returns_none():
    assert brand_normalize(None) is None


def test_empty_string_returns_none():
    assert brand_normalize("") is None


def test_known_alias_resolves():
    assert brand_normalize("mcdonalds") == "McDonald's"
    assert brand_normalize("McDonald's") == "McDonald's"


def test_symbol_stripping_in_key():
    # "Coca-Cola®" → key "coca-cola" → resolves to "Coca-Cola"
    assert brand_normalize("Coca-Cola®") == "Coca-Cola"
    assert brand_normalize("Coke™") == "Coca-Cola"


def test_unknown_brand_returns_stripped():
    result = brand_normalize("  BrandXYZ  ")
    assert result == "BrandXYZ"


def test_whitespace_collapse():
    result = brand_normalize("  Some   Brand  ")
    assert result == "Some   Brand".strip()
