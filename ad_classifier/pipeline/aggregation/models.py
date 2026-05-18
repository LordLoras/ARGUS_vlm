from __future__ import annotations

from pydantic import Field

from ad_classifier.models.classification import OCRQuality
from ad_classifier.models.common import EvidenceItem, StrictModel
from ad_classifier.models.iab import IABCategory
from ad_classifier.models.marketing import MarketingEntities


class AggregationConfig(StrictModel):
    pass


class SimilarAd(StrictModel):
    ad_id: str
    overall_score: float
    visual_score: float | None = None
    text_score: float | None = None
    verdict: str = ""
    differences: list[dict] = Field(default_factory=list)


class RelatedAds(StrictModel):
    exact_duplicate_of: str | None = None
    near_duplicate_of: str | None = None
    semantically_similar: list[SimilarAd] = Field(default_factory=list)


class FinalAdClassification(StrictModel):
    ad_id: str
    primary_category: str
    iab_category: IABCategory | None = None
    risk_labels: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sensitive_category: bool = False
    ocr_quality: OCRQuality | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    marketing_entities: MarketingEntities = Field(default_factory=MarketingEntities)
    campaigns: list[dict] = Field(default_factory=list)
    related_ads: RelatedAds = Field(default_factory=RelatedAds)
    embeddings: dict = Field(
        default_factory=lambda: {"text_model": "", "visual_model": "", "indexed_in": "sqlite-vec"}
    )
    model_outputs: dict = Field(default_factory=lambda: {"ocr": {}, "paddlevl": {}, "vlm": {}})
    debug: dict = Field(
        default_factory=lambda: {
            "selected_frames": [],
            "dropped_frames": [],
            "rules_triggered": [],
            "dropped_labels": [],
        }
    )
    vlm_model: str = ""
    vlm_prompt_version: str = ""
    pipeline_version: str = ""
