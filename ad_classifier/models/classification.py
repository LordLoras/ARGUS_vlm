from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ad_classifier.models.ads import utc_now
from ad_classifier.models.common import EvidenceItem, StrictModel

Decision = Literal["allow", "review"]
OcrQualityLevel = Literal["good", "mixed", "poor"]


class OCRQuality(StrictModel):
    overall: OcrQualityLevel
    possible_errors: list[str] = Field(default_factory=list)
    missed_text: list[str] = Field(default_factory=list)


class ClassificationRecord(StrictModel):
    ad_id: str
    primary_category: str | None = None
    risk_labels: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    decision: Decision
    needs_human_review: bool
    ocr_quality: OCRQuality | None = None
    vlm_raw: dict = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    vlm_model: str
    vlm_prompt_version: str
    embedder_text_model: str
    embedder_visual_model: str
    pipeline_version: str
    created_at: datetime = Field(default_factory=utc_now)
