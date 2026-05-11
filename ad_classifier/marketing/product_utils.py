from __future__ import annotations

import re
from pathlib import Path

_GARBLED_YEAR_PREFIX = re.compile(r"^\s*20[A-Z]{1,4}\d{1,4}\s+", re.IGNORECASE)
_GENERIC_VEHICLE_MAKES_PATH = Path(__file__).with_name("vehicle_makes.txt")
_MERGED_MODEL_INDICATORS = re.compile(
    r"(?:AND|OR|MODELS?|SERIES)(?:[A-Z]{3,})", re.IGNORECASE
)
_ALL_CAPS_NO_YEAR = re.compile(r"^[A-Z\s\d/()\-]+$")

_VEHICLE_MAKES_CACHE: set[str] | None = None


def _compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _normalize_product_case(product: str) -> str:
    if not product:
        return product
    if not _ALL_CAPS_NO_YEAR.match(product):
        return product
    has_year_prefix = bool(re.match(r"^\s*20\d{2}\s", product))
    if not has_year_prefix:
        return product
    year_match = re.match(r"^(\s*20\d{2}\s+)(.*)", product)
    if not year_match:
        return product
    year_part = year_match.group(1)
    rest = year_match.group(2)
    return year_part + _title_case_rest(rest)


def _title_case_rest(s: str) -> str:
    words = s.split()
    result = []
    for word in words:
        if word.upper() in {"LE", "4x4", "4x2", "AWD", "FWD", "RWD", "PHEV", "EV"}:
            result.append(word.upper())
        elif "-" in word:
            result.append("-".join(p.capitalize() for p in word.split("-")))
        else:
            result.append(word.capitalize())
    return " ".join(result)


def repair_products(products: list[str], brand_name: str | None) -> list[str]:
    from ad_classifier.marketing._utils import _clean_entity_text

    cleaned_items: list[str] = []
    repaired: list[str] = []
    for product in products:
        cleaned = _clean_entity_text(product)
        cleaned = _GARBLED_YEAR_PREFIX.sub("", cleaned).strip()
        if brand_name:
            cleaned = re.sub(
                rf"^\s*{re.escape(brand_name)}\s+",
                "",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
            cleaned = re.sub(
                rf"^\s*(20\d{{2}})\s+{re.escape(brand_name)}\s+",
                r"\1 ",
                cleaned,
                flags=re.IGNORECASE,
            ).strip()
        cleaned = cleaned.strip(" ,-")
        if len(cleaned) < 2:
            continue
        if _MERGED_MODEL_INDICATORS.search(cleaned):
            continue
        cleaned = _normalize_product_case(cleaned)
        cleaned_items.append(cleaned)

    has_specific_vehicle = any(_is_specific_vehicle_product(item) for item in cleaned_items)
    brand_key = _compact_key(brand_name or "")
    for cleaned in cleaned_items:
        if _is_generic_vehicle_make_product(cleaned, brand_key, has_specific_vehicle):
            continue
        if _compact_key(cleaned) not in {_compact_key(item) for item in repaired}:
            repaired.append(cleaned)
    return repaired


def _merge_products(left: list[str], right: list[str]) -> list[str]:
    merged = list(left)
    for item in right:
        if not item:
            continue
        if any(_compact_key(item) == _compact_key(existing) for existing in merged):
            continue
        if any(_is_weaker_product_variant(item, existing) for existing in merged):
            continue
        merged = [existing for existing in merged if not _is_weaker_product_variant(existing, item)]
        merged.append(item)
    return merged


def _is_weaker_product_variant(candidate: str, existing: str) -> bool:
    candidate_tokens = _product_tokens(candidate)
    existing_tokens = _product_tokens(existing)
    if not candidate_tokens or not existing_tokens:
        return False
    return candidate_tokens < existing_tokens


def _is_specific_vehicle_product(value: str) -> bool:
    tokens = _product_tokens(value)
    return len(tokens) >= 2 and any(t.isdigit() for t in tokens)


def _load_vehicle_makes() -> set[str]:
    try:
        return {
            line.strip().lower()
            for line in _GENERIC_VEHICLE_MAKES_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
    except FileNotFoundError:
        return set()


def _vehicle_makes() -> set[str]:
    global _VEHICLE_MAKES_CACHE
    if _VEHICLE_MAKES_CACHE is None:
        _VEHICLE_MAKES_CACHE = _load_vehicle_makes()
    return _VEHICLE_MAKES_CACHE


def _is_generic_vehicle_make_product(
    value: str,
    brand_key: str,
    has_specific_vehicle: bool,
) -> bool:
    key = _compact_key(value)
    if key not in _vehicle_makes():
        return False
    return has_specific_vehicle or (brand_key and key in brand_key)


def _product_tokens(value: str) -> set[str]:
    normalized = value.lower().replace("4-door", "4door").replace("4x4", "4x4")
    return set(re.findall(r"[a-z0-9]+", normalized))
