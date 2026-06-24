"""Campaign grouping: roll multiple creatives/variants/cross-posts into one event.

A single launch often shows up as a 15s + 30s cut, regional variants, and a cross-post
to the newsroom. Grouping by ``brand + campaign phrase + date-window`` collapses those
into one ``campaign_group_id`` so the feed reports "Toyota launched campaign X" once,
not ten times. (Thumbnail-pHash variant matching is a documented later refinement.)
"""

from __future__ import annotations

from datetime import datetime

from ad_classifier.entity_graph.utils import normalize_name
from ad_classifier.intelligence_crawler.models import RawSourceItem
from ad_classifier.intelligence_crawler.timeutils import as_utc

# Generic words that don't help identify a specific campaign.
_PHRASE_STOPWORDS = {
    "the",
    "a",
    "an",
    "new",
    "official",
    "ad",
    "ads",
    "advert",
    "commercial",
    "spot",
    "tvc",
    "video",
    "trailer",
    "presents",
    "introducing",
    "launch",
    "campaign",
    "for",
    "with",
    "your",
    "our",
    "you",
    "us",
    "and",
    "to",
    "of",
    "in",
    "on",
}


def derive_campaign_phrase(title: str | None) -> str:
    tokens = [t for t in normalize_name(title or "").split() if t and t not in _PHRASE_STOPWORDS]
    return " ".join(tokens[:6])


def campaign_group_key(brand_name: str, item: RawSourceItem, *, fallback: datetime) -> str:
    """Stable grouping key: brand + campaign phrase + ISO-week bucket."""
    phrase = derive_campaign_phrase(item.title) or "general"
    when = as_utc(item.published_at) or as_utc(fallback)
    assert when is not None
    year, week, _ = when.isocalendar()
    return f"{normalize_name(brand_name)}|{phrase}|{year}-w{week:02d}"


def campaign_title(item: RawSourceItem) -> str | None:
    return item.title.strip() if item.title else None
