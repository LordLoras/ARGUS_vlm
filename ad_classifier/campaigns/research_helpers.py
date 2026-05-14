from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any


def json_value(raw: Any) -> Any:
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def json_list(raw: Any) -> list[Any]:
    parsed = json_value(raw)
    return parsed if isinstance(parsed, list) else []


def json_dict(raw: Any) -> dict[str, Any]:
    parsed = json_value(raw)
    return parsed if isinstance(parsed, dict) else {}


def text_values(value: Any) -> list[str]:
    values: list[str] = []
    items = value if isinstance(value, list) else []
    for item in items:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("text") or item.get("value") or item.get("raw_text")
        else:
            text = None
        cleaned = clean(text)
        if cleaned:
            values.append(cleaned)
    return values


def price_values(value: Any) -> list[str]:
    values: list[str] = []
    items = value if isinstance(value, list) else []
    for item in items:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("text")
            if not text and item.get("amount") is not None:
                currency = item.get("currency") or ""
                text = f"{currency}{item['amount']}".strip()
        else:
            text = None
        cleaned = clean(text)
        if cleaned:
            values.append(cleaned)
    return values


def campaign_suggestion_values(items: list[Any]) -> list[str]:
    values: list[str] = []
    for item in items:
        if isinstance(item, dict):
            name = clean(item.get("name"))
            if name:
                values.append(name)
    return values


def string_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    values: list[str] = []
    for item in value:
        cleaned = clean(item)
        if cleaned:
            values.append(cleaned)
    return values


def split_products(value: Any) -> list[str]:
    cleaned = clean(value)
    if not cleaned:
        return []
    return [part for part in (clean(item) for item in cleaned.split(",")) if part]


def small_print_count(items: list[Any]) -> int:
    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("is_small_print") is True or "small" in str(item.get("text") or "").casefold():
            count += 1
    return count


def top_counts(values: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    cleaned = [clean(value) for value in values]
    counter = Counter(value for value in cleaned if value)
    total = sum(counter.values())
    return [
        {"value": value, "count": count, "share": round(count / total, 3) if total else 0.0}
        for value, count in counter.most_common(limit)
    ]


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def date_range(values: list[Any]) -> tuple[str | None, str | None]:
    cleaned = sorted(value for value in (clean(v) for v in values) if value)
    if not cleaned:
        return None, None
    return cleaned[0], cleaned[-1]


def span_days(first_seen: str | None, last_seen: str | None) -> int | None:
    first = parse_datetime(first_seen)
    last = parse_datetime(last_seen)
    if first is None or last is None:
        return None
    return max((last.date() - first.date()).days, 0)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def creative_value(ad: dict[str, Any], format_key: str | None, attributes_key: str | None) -> str | None:
    if format_key:
        value = (ad.get("creative_format") or {}).get(format_key)
        if clean(value):
            return clean(value)
    if attributes_key:
        return clean((ad.get("creative_attributes") or {}).get(attributes_key))
    return None


def creative_bool(ad: dict[str, Any], format_key: str | None, attributes_key: str | None) -> bool:
    if format_key and (ad.get("creative_format") or {}).get(format_key) is True:
        return True
    return bool(attributes_key and (ad.get("creative_attributes") or {}).get(attributes_key) is True)


def first_value(items: list[dict[str, Any]]) -> str | None:
    first = first_count(items)
    return str(first["value"]) if first else None


def first_count(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return items[0] if items else None


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
