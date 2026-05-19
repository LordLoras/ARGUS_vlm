from __future__ import annotations

import json
import re
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


def top_counts(values: Any, *, limit: int | None = 8) -> list[dict[str, Any]]:
    cleaned = [clean(value) for value in values]
    counter = Counter(value for value in cleaned if value)
    total = sum(counter.values())
    return [
        {"value": value, "count": count, "share": round(count / total, 3) if total else 0.0}
        for value, count in counter.most_common(limit)
    ]


def runtime_bucket_counts(ads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for ad in ads:
        duration = _duration_seconds(ad.get("duration_ms"))
        if duration is None:
            counter["Unknown"] += 1
            continue
        bucket = _runtime_bucket(duration)
        counter[bucket] += 1

    total = sum(counter.values())
    return [
        {"value": value, "count": count, "share": round(count / total, 3) if total else 0.0}
        for value, count in sorted(counter.items(), key=lambda item: _runtime_sort_key(item[0]))
    ]


def product_family_counts(
    ads: list[dict[str, Any]], *, limit: int | None = 12
) -> list[dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}
    total_mentions = 0
    for ad in ads:
        duration_ms = int(ad.get("duration_ms") or 0)
        seen_in_ad: set[str] = set()
        for product in ad.get("products", []):
            variant = clean(product)
            if not variant:
                continue
            family = product_family_name(variant)
            key = family.casefold()
            if key not in families:
                families[key] = {
                    "value": family,
                    "count": 0,
                    "ad_ids": set(),
                    "total_duration_ms": 0,
                    "variants": Counter(),
                }
            families[key]["count"] += 1
            families[key]["variants"][variant] += 1
            families[key]["ad_ids"].add(ad.get("ad_id"))
            if key not in seen_in_ad:
                families[key]["total_duration_ms"] += duration_ms
                seen_in_ad.add(key)
            total_mentions += 1

    items: list[dict[str, Any]] = []
    for family in families.values():
        ad_ids = sorted(ad_id for ad_id in family["ad_ids"] if ad_id)
        variants_total = sum(family["variants"].values())
        items.append(
            {
                "value": family["value"],
                "count": family["count"],
                "share": round(family["count"] / total_mentions, 3) if total_mentions else 0.0,
                "ad_count": len(ad_ids),
                "total_duration_ms": family["total_duration_ms"] or None,
                "ad_ids": ad_ids,
                "variants": [
                    {
                        "value": value,
                        "count": count,
                        "share": round(count / variants_total, 3) if variants_total else 0.0,
                    }
                    for value, count in family["variants"].most_common()
                ],
            }
        )

    items.sort(key=lambda item: (-int(item["count"]), str(item["value"]).casefold()))
    return items if limit is None else items[:limit]


def product_family_name(value: str) -> str:
    text = clean(value)
    if not text:
        return value
    normalized = re.sub(r"\bMY\s*(?:19|20)\d{2}\b", " ", text, flags=re.IGNORECASE)
    normalized = re.sub(r"\b(?:19|20)\d{2}\b", " ", normalized)
    normalized = re.sub(r"\b['’](?:\d{2})\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.strip(" -_/,:")
    return normalized or text


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


def creative_value(
    ad: dict[str, Any], format_key: str | None, attributes_key: str | None
) -> str | None:
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
    return bool(
        attributes_key and (ad.get("creative_attributes") or {}).get(attributes_key) is True
    )


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


def _duration_seconds(value: Any) -> int | None:
    if not isinstance(value, int | float) or value <= 0:
        return None
    return int(round(float(value) / 1000))


def _runtime_bucket(seconds: int) -> str:
    standard = [6, 10, 15, 20, 30, 45, 60, 90]
    nearest = min(standard, key=lambda item: abs(item - seconds))
    if abs(nearest - seconds) <= 2:
        seconds = nearest
    return f"{seconds}s"


def _runtime_sort_key(value: str) -> tuple[int, str]:
    if value == "Unknown":
        return (999_999, value)
    number = value.rstrip("s")
    try:
        return (int(number), value)
    except ValueError:
        return (999_998, value)
