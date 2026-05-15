from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

from ad_classifier.config import CampaignDiscoveryConfig


@dataclass(frozen=True)
class CampaignSignal:
    name: str
    key: str
    confidence: float


def campaign_suggestions_from_row(
    row: sqlite3.Row,
    brand: str,
    config: CampaignDiscoveryConfig,
) -> tuple[CampaignSignal, ...]:
    if not config.use_campaign_suggestions:
        return ()
    raw = _row_value(row, "campaign_suggestions_json")
    if not raw:
        values = []
    else:
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            values = []
        if not isinstance(values, list):
            values = []

    signals: list[CampaignSignal] = []
    for value in values:
        name = ""
        confidence = 1.0
        if isinstance(value, dict):
            name = str(value.get("name") or "").strip()
            confidence = _coerce_confidence(value.get("confidence"), default=1.0)
        elif isinstance(value, str):
            name = value.strip()
        if not name or confidence < config.min_campaign_signal_confidence:
            continue

        key = campaign_signal_key(name, brand)
        if not key:
            continue
        signals.append(
            CampaignSignal(
                name=clean_display_text(name),
                key=key,
                confidence=confidence,
            )
        )

    existing_keys = {signal.key for signal in signals}
    badge_confidence = 0.9
    if badge_confidence < config.min_campaign_signal_confidence:
        return tuple(signals)
    for name in _campaign_badges_from_row(row):
        key = campaign_signal_key(name, brand)
        if not key or key in existing_keys:
            continue
        existing_keys.add(key)
        signals.append(
            CampaignSignal(
                name=clean_display_text(name),
                key=key,
                confidence=badge_confidence,
            )
        )
    return tuple(signals)


def signal_display_name(cluster, signal_key: str) -> str:
    names: dict[str, str] = {}
    scores: Counter[str] = Counter()
    confidence_totals: dict[str, float] = defaultdict(float)
    for ad in cluster:
        for signal in ad.campaign_suggestions:
            if signal.key != signal_key:
                continue
            compact = canonical_text(signal.name)
            if not compact:
                continue
            names.setdefault(compact, signal.name)
            scores[compact] += 1
            confidence_totals[compact] += signal.confidence
    if not scores:
        return signal_key.title()
    winner = min(
        scores,
        key=lambda key: (-scores[key], -confidence_totals[key], names[key].casefold()),
    )
    return names[winner]


def campaign_signal_key(name: str, brand: str) -> str:
    key = canonical_text(name)
    brand_key = canonical_text(brand)
    if brand_key and key.startswith(f"{brand_key} "):
        key = key[len(brand_key) + 1 :]
    key = re.sub(r"^(the|a|an)\s+", "", key)
    return key


def strip_brand_prefix(value: str, brand: str) -> str:
    key = canonical_text(value)
    brand_key = canonical_text(brand)
    if brand_key and key.startswith(f"{brand_key} "):
        return clean_display_text(value[len(brand) :])
    return clean_display_text(value)


def starts_with_brand(value: str, brand: str) -> bool:
    key = canonical_text(value)
    brand_key = canonical_text(brand)
    return bool(brand_key and (key == brand_key or key.startswith(f"{brand_key} ")))


def canonical_text(value: str) -> str:
    text = value.replace("&", " and ").casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_display_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" -_\t\r\n")


def _campaign_badges_from_row(row: sqlite3.Row) -> list[str]:
    raw = _row_value(row, "social_proof_json")
    if not raw:
        return []
    try:
        social = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(social, dict):
        return []
    badges = social.get("badges")
    if not isinstance(badges, list):
        return []

    names: list[str] = []
    for badge in badges:
        text = clean_display_text(str(badge or ""))
        if not text or not _is_campaign_like_badge(text):
            continue
        names.append(_badge_campaign_name(text))
    return names


def _is_campaign_like_badge(text: str) -> bool:
    lowered = canonical_text(text)
    return bool(
        re.search(
            r"\b(partner|sponsor|presented|official|anniversary|centennial|bicentennial|america 250)\b",
            lowered,
        )
    )


def _badge_campaign_name(text: str) -> str:
    match = re.search(
        r"(?:proud\s+)?(?:official\s+)?(?:partner|sponsor)\s+(?:of|for|with)\s+(.+)",
        text,
        re.IGNORECASE,
    )
    if match:
        return clean_display_text(match.group(1)) or text
    return text


def _row_value(row: sqlite3.Row, key: str) -> object | None:
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def _coerce_confidence(value: object, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
