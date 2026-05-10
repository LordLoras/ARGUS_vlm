from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ad_classifier.models.classification import ClassificationRecord, Decision
from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import MarketingEntities


class AggregationConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    allow_threshold: float = Field(default=0.75, ge=0.0, le=1.0)


class SimilarAd(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ad_id: str
    overall_score: float
    visual_score: float | None = None
    text_score: float | None = None
    verdict: str = ""
    differences: list[dict] = Field(default_factory=list)


class RelatedAds(BaseModel):
    model_config = ConfigDict(extra="ignore")

    exact_duplicate_of: str | None = None
    near_duplicate_of: str | None = None
    semantically_similar: list[SimilarAd] = Field(default_factory=list)


class FinalAdClassification(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ad_id: str
    primary_category: str
    risk_labels: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    decision: Decision
    needs_human_review: bool
    evidence: list[EvidenceItem] = Field(default_factory=list)
    marketing_entities: MarketingEntities = Field(default_factory=MarketingEntities)
    related_ads: RelatedAds = Field(default_factory=RelatedAds)
    vlm_model: str = ""
    vlm_prompt_version: str = ""
    pipeline_version: str = ""
