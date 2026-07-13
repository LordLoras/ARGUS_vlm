"""Canonical source reliability tiers used by config, API, UI, and scoring."""

from __future__ import annotations

from ad_classifier.intelligence_crawler.models import Tier

CANONICAL_SOURCE_TIERS: dict[str, Tier] = {
    "meta_ad_library_ui": "A",
    "google_atc": "B",
    "youtube_channel": "C",
    "rss": "C",
    "mock": "A",
}


def canonical_tier(source_type: str, fallback: Tier = "C") -> Tier:
    return CANONICAL_SOURCE_TIERS.get(source_type, fallback)
