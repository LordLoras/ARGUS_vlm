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
    raw = row["campaign_suggestions_json"]
    if not raw:
        return ()
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(values, list):
        return ()

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


def _coerce_confidence(value: object, *, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
