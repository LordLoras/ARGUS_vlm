from __future__ import annotations

from typing import Literal

from pydantic import Field

from ad_classifier.models.common import StrictModel

SimilarityVerdict = Literal[
    "near_duplicate",
    "same_campaign_different_sku",
    "same_campaign_different_offer",
    "similar_messaging_different_brand",
    "related",
    "unrelated",
]


class FieldDifference(StrictModel):
    field: str
    left: list[str] | str | None
    right: list[str] | str | None


class SimilarAdRecord(StrictModel):
    ad_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    visual_score: float | None = Field(default=None, ge=0.0, le=1.0)
    text_score: float | None = Field(default=None, ge=0.0, le=1.0)
    verdict: SimilarityVerdict
    differences: list[FieldDifference] = Field(default_factory=list)
