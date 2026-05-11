from __future__ import annotations

import re

_DENSITY_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def max_density(left: str, right: str) -> str:
    return left if _DENSITY_RANK[left] >= _DENSITY_RANK[right] else right


def merge_strings(left: list[str], right: list[str]) -> list[str]:
    merged = list(left)
    for item in right:
        if item and item not in merged:
            merged.append(item)
    return merged


def currency_symbol(currency: str | None) -> str:
    normalized = (currency or "$").strip().upper()
    if normalized in {"USD", "US$", "$"}:
        return "$"
    return currency or "$"


def format_amount(amount: float) -> str:
    if float(amount).is_integer():
        return f"{int(amount):,}"
    return f"{amount:,.2f}".rstrip("0").rstrip(".")


def format_price(currency: str | None, amount: float) -> str:
    return f"{currency_symbol(currency)}{format_amount(amount)}"


def compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _clean_entity_text(text: str) -> str:
    from ad_classifier.marketing.ocr_normalize import normalize_ocr_text

    text = normalize_ocr_text(text)
    text = re.sub(r"\s+([!?.,;:])", r"\1", text)
    return text.strip(" ,;:-")
