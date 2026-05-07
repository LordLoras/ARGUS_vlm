from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from ad_classifier.models.common import StrictModel

AdStatus = Literal["new", "processing", "completed", "failed", "duplicate", "review"]


def utc_now() -> datetime:
    return datetime.now(UTC)


class AdRecord(StrictModel):
    id: str
    source_path: str
    ingested_at: datetime = Field(default_factory=utc_now)
    duration_ms: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    fps: float | None = Field(default=None, ge=0)
    status: AdStatus | None = None
    brand_name: str | None = None
    brand_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    advertiser_name: str | None = None
    website_domain: str | None = None
    phone_number: str | None = None
    landing_page_domain: str | None = None
    products_text: str | None = None
    primary_category: str | None = None
    decision: str | None = None
    source_hash: str | None = None
    phash_mean: str | None = None


class FrameRecord(StrictModel):
    id: int | None = None
    ad_id: str
    frame_index: int = Field(ge=0)
    time_ms: int = Field(ge=0)
    path: str
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    kept: bool = True
    drop_reason: str | None = None
    phash: str | None = None
    blur_score: float | None = Field(default=None, ge=0)


class OCRItemRecord(StrictModel):
    id: int | None = None
    frame_id: int
    engine: str
    text: str
    bbox_json: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TranscriptSegmentRecord(StrictModel):
    id: int | None = None
    ad_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class RuleTriggerRecord(StrictModel):
    id: int | None = None
    ad_id: str
    rule_id: str
    category: str | None = None
    risk_label: str | None = None
    severity: str | None = None
    evidence_text: str | None = None
    time_ms: int | None = Field(default=None, ge=0)
    frame_index: int | None = Field(default=None, ge=0)
