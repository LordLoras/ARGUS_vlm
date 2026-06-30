"""Pydantic models for the intelligence crawler (StrictModel: extra fields forbidden)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ad_classifier.models.common import StrictModel

Market = Literal["US"]
Tier = Literal["A", "B", "C"]
SignalType = Literal[
    "new_ad_upload",
    "campaign_launch",
    "new_campaign_variant",
    "offer_change",
    "product_push",
    "official_press_mention",
]
SignalStatus = Literal[
    "candidate",
    "corroborated",
    "matched_local",
    "accepted",
    "dismissed",
    "stale",
]
RunStatus = Literal["queued", "running", "completed", "failed", "degraded"]


class WatchedBrand(StrictModel):
    brand_name: str
    normalized_name: str
    origin: Literal["graph", "seed", "both"]
    graph_node_id: str | None = None
    has_verified_source: bool = False


class IntelSource(StrictModel):
    """A monitored origin of data for one brand (a YouTube channel, a newsroom feed…).

    ``source_type`` is an open string keyed to the adapter registry, deliberately not an
    enum: adding a new source kind must not require editing this model.
    """

    id: str
    brand_name: str
    market: Market = "US"
    source_type: str
    tier: Tier = "B"
    url: str | None = None
    platform: str | None = None
    platform_id: str | None = None
    enabled: bool = False
    poll_interval_hours: float = 12.0
    source_activated_at: datetime | None = None
    allowed_domains: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)
    notes: str | None = None


class SourceState(StrictModel):
    source_id: str
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    next_due_at: datetime | None = None
    last_error: str | None = None
    consecutive_errors: int = 0
    etag: str | None = None
    last_modified: str | None = None
    watermark: str | None = None
    lease_until: datetime | None = None
    lease_owner: str | None = None


class RawSourceItem(StrictModel):
    """What an adapter yields before persistence/normalization.

    ``external_id`` must be stable for the item (video id, RSS GUID, or a canonical-URL
    hash) — it is the dedup key that makes re-polling idempotent.
    """

    external_id: str
    url: str
    canonical_url: str | None = None
    resource_type: str = "page"
    title: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    thumbnail_url: str | None = None
    duration_ms: int | None = None
    raw: dict = Field(default_factory=dict)


class SourcePollResult(StrictModel):
    source_id: str
    items: list[RawSourceItem] = Field(default_factory=list)
    new_watermark: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    errors: list[str] = Field(default_factory=list)


class IntelResource(StrictModel):
    id: str
    source_id: str
    run_id: str | None = None
    resource_type: str
    url: str | None = None
    canonical_url: str | None = None
    platform: str | None = None
    platform_id: str | None = None
    content_hash: str | None = None
    title: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    first_seen_at: datetime
    fetched_at: datetime
    is_backfill: bool = False
    metadata: dict = Field(default_factory=dict)


class IntelArtifactSummary(StrictModel):
    screenshot_count: int = 0
    image_source_count: int = 0
    video_source_count: int = 0
    video_poster_count: int = 0
    background_image_source_count: int = 0
    link_count: int = 0
    media_asset_count: int = 0


class IntelResourceArtifact(StrictModel):
    artifact_type: str
    label: str
    url: str | None = None
    path: str | None = None
    text: str | None = None


class IntelResourceView(StrictModel):
    id: str
    brand_name: str
    source_id: str
    source_type: str
    resource_type: str
    url: str | None = None
    platform_id: str | None = None
    title: str | None = None
    description: str | None = None
    published_at: datetime | None = None
    first_seen_at: datetime
    fetched_at: datetime
    is_backfill: bool = False
    artifact_summary: IntelArtifactSummary = Field(default_factory=IntelArtifactSummary)
    artifacts: list[IntelResourceArtifact] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class IntelBrandOverview(StrictModel):
    brand_name: str
    source_count: int = 0
    enabled_source_count: int = 0
    resource_count: int = 0
    backfill_resource_count: int = 0
    signal_count: int = 0
    latest_resource_seen_at: datetime | None = None
    latest_signal_seen_at: datetime | None = None
    source_types: list[str] = Field(default_factory=list)
    artifact_summary: IntelArtifactSummary = Field(default_factory=IntelArtifactSummary)


class IntelAdapterDescriptor(StrictModel):
    source_type: str
    label: str
    target_label: str
    target_placeholder: str
    helper_text: str
    default_tier: Tier = "B"
    platform: str | None = None
    requires_url: bool = False
    requires_platform_id: bool = False
    config: dict = Field(default_factory=dict)
    provides: list[str] = Field(default_factory=list)


class IntelEvidence(StrictModel):
    id: str
    signal_id: str
    resource_id: str | None = None
    source_id: str | None = None
    evidence_type: str
    url: str | None = None
    text: str | None = None
    published_at: datetime | None = None
    confidence: float = 0.0


class IntelCampaignGroup(StrictModel):
    id: str
    brand_name: str
    group_key: str
    title: str | None = None
    first_seen_at: datetime
    last_activity_at: datetime
    status: SignalStatus = "candidate"


class IntelSignal(StrictModel):
    id: str
    brand_name: str
    campaign_group_id: str | None = None
    signal_type: SignalType
    status: SignalStatus = "candidate"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    title: str
    summary: str | None = None
    campaign_name: str | None = None
    products: list[str] = Field(default_factory=list)
    first_seen_at: datetime
    source_published_at: datetime | None = None
    last_seen_at: datetime
    score_breakdown: dict = Field(default_factory=dict)
    evidence: list[IntelEvidence] = Field(default_factory=list)


class IntelMatch(StrictModel):
    id: str
    signal_id: str
    target_type: Literal["ad", "campaign", "product", "brand"]
    target_id: str
    match_score: float
    reasons: list[str] = Field(default_factory=list)


class SourceRunItem(StrictModel):
    source_id: str
    status: Literal["polled", "skipped", "failed"]
    new_resources: int = 0
    new_signals: int = 0
    backfilled: int = 0
    filtered: int = 0  # live items recorded but not emitted (failed the ad-likelihood gate)
    baseline: bool = False
    reason: str | None = None


class CrawlRunSummary(StrictModel):
    run_id: str
    status: RunStatus
    source_count: int = 0
    resource_count: int = 0
    signal_count: int = 0
    items: list[SourceRunItem] = Field(default_factory=list)
    error: str | None = None


class DigestEntry(StrictModel):
    brand_name: str
    campaign_group_id: str | None = None
    headline: str
    signal_count: int
    top_confidence: float
    signal_ids: list[str] = Field(default_factory=list)
    evidence_urls: list[str] = Field(default_factory=list)
