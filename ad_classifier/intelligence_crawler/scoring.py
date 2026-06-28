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


def ad_likelihood(item: RawSourceItem, config: ScoringConfig) -> tuple[float, dict]:
    """Heuristic 0..1 score that an item is an *ad/commercial* (not other content).

    Combines a keyword cue (title/description) with a duration cue when available — ads
    cluster at ~5-95s; long-form content is unlikely to be an ad. Duration comes from
    Data-API enrichment; without it the score relies on keywords only. Returns
    (score, breakdown) so the reasoning is persisted on the signal.
    """
    breakdown: dict = {}
    score = 0.0

    keyword = is_ad_like(item, config.ad_like_terms)
    breakdown["keyword"] = keyword
    if keyword:
        score += 0.5

    duration_ms = item.duration_ms
    breakdown["duration_ms"] = duration_ms
    if duration_ms is not None:
        seconds = duration_ms / 1000.0
        if seconds <= config.ad_typical_max_seconds:
            score += 0.5
            breakdown["duration_class"] = "ad_typical"
        elif seconds <= config.ad_longform_seconds:
            score += 0.2
            breakdown["duration_class"] = "medium"
        else:
            score = min(score, 0.25)  # long-form veto: very unlikely to be an ad
            breakdown["duration_class"] = "long_form"
    else:
        breakdown["duration_class"] = "unknown"

    value = max(0.0, min(1.0, score))
    breakdown["ad_likelihood"] = value
    return value, breakdown


def is_ad_signal_candidate(item: RawSourceItem, config: ScoringConfig) -> bool:
    """Whether a *live* item should emit an ad/campaign signal.

    Video items must clear the ad-likelihood threshold (so a brand channel's non-ad
    content does not become a `new_ad_upload`). Non-video items (press releases) are
    announcements and always pass.
    """
    if (item.resource_type or "").lower() not in {"video", "youtube_video"}:
        return True
    likelihood, _ = ad_likelihood(item, config)
    return likelihood >= config.min_ad_likelihood


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
    likelihood, likelihood_breakdown = ad_likelihood(item, config)
    ad_bonus = config.ad_likeness_bonus * likelihood
    corroboration = min(config.corroboration_bonus * corroborating_count, config.corroboration_cap)
    confidence = max(0.0, min(1.0, tier_weight + ad_bonus + corroboration))

    status: SignalStatus = (
        "corroborated"
        if corroborating_count >= 1 or confidence >= config.corroborated_min_confidence
        else "candidate"
    )
    breakdown = {
        "tier_weight": tier_weight,
        "ad_bonus": round(ad_bonus, 4),
        "corroboration": corroboration,
        "corroborating_count": corroborating_count,
        **likelihood_breakdown,
    }
    return confidence, status, breakdown


def is_stale(published_at: datetime | None, now: datetime, stale_after_days: int) -> bool:
    published = as_utc(published_at)
    now_utc = as_utc(now)
    if published is None or now_utc is None:
        return False
    return (now_utc - published) > timedelta(days=stale_after_days)
