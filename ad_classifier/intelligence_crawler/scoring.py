"""Confidence scoring + signal typing + staleness.

v1 keeps a deliberately simple, explainable 3-term model and persists the full
breakdown so it can grow into a richer model later without a schema change:

    confidence = tier_weight + ad_likeness_bonus + corroboration   (clamped 0..1)
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ad_classifier.entity_graph.utils import normalize_name
from ad_classifier.intelligence_crawler.config import ScoringConfig
from ad_classifier.intelligence_crawler.models import (
    RawSourceItem,
    SignalStatus,
    SignalType,
    Tier,
)
from ad_classifier.intelligence_crawler.timeutils import as_utc


def is_ad_like(item: RawSourceItem, terms: list[str]) -> bool:
    haystack = normalize_name(" ".join([item.title or "", item.description or ""]))
    return any(normalize_name(term) in haystack for term in terms if term)


def classify_signal_type(item: RawSourceItem) -> SignalType:
    resource_type = (item.resource_type or "").lower()
    if resource_type in {"video", "youtube_video"}:
        return "new_ad_upload"
    if resource_type in {"press", "article", "press_release"}:
        return "official_press_mention"
    return "campaign_launch"


def score_signal(
    *,
    tier: Tier,
    item: RawSourceItem,
    corroborating_count: int,
    config: ScoringConfig,
) -> tuple[float, SignalStatus, dict]:
    """Return (confidence, status, breakdown). ``corroborating_count`` = extra
    independent resources/sources already supporting this campaign group."""
    tier_weight = float(config.tier_weights.get(tier, 0.0))
    ad_like = is_ad_like(item, config.ad_like_terms)
    ad_bonus = config.ad_likeness_bonus if ad_like else 0.0
    corroboration = min(config.corroboration_bonus * corroborating_count, config.corroboration_cap)
    confidence = max(0.0, min(1.0, tier_weight + ad_bonus + corroboration))

    status: SignalStatus = (
        "corroborated"
        if corroborating_count >= 1 or confidence >= config.corroborated_min_confidence
        else "candidate"
    )
    breakdown = {
        "tier_weight": tier_weight,
        "ad_likeness": ad_bonus,
        "ad_like": ad_like,
        "corroboration": corroboration,
        "corroborating_count": corroborating_count,
    }
    return confidence, status, breakdown


def is_stale(published_at: datetime | None, now: datetime, stale_after_days: int) -> bool:
    published = as_utc(published_at)
    now_utc = as_utc(now)
    if published is None or now_utc is None:
        return False
    return (now_utc - published) > timedelta(days=stale_after_days)
