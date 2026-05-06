from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ad_classifier.models.classification import Decision, OcrQualityLevel

# VLM response models use extra="ignore" so unknown fields from the model don't error.


class _VLMBase(BaseModel):
    model_config = ConfigDict(extra="ignore")


class VLMLogoEvidence(_VLMBase):
    time_ms: int = 0
    frame_index: int = 0
    reason: str = ""


class VLMBrand(_VLMBase):
    name: str | None = None
    logo_present: bool = False
    logo_evidence: list[VLMLogoEvidence] = Field(default_factory=list)
    tagline: str | None = None


class VLMPrice(_VLMBase):
    amount: float = 0.0
    currency: str = ""
    frame_index: int = 0
    time_ms: int = 0
    discounted_from: float | None = None
    discount_pct: float | None = None


class VLMOffer(_VLMBase):
    type: str = "other"
    value: str = ""
    expiry_text: str | None = None
    expiry_resolved: str | None = None
    promo_code: str | None = None
    scarcity_signals: list[str] = Field(default_factory=list)
    urgency_signals: list[str] = Field(default_factory=list)


class VLMCTA(_VLMBase):
    text: str = ""
    destination_hint: str | None = None
    time_ms: int = 0
    frame_index: int = 0


class VLMSocialProof(_VLMBase):
    rating: float | None = None
    rating_count: str | None = None
    testimonials: list[str] = Field(default_factory=list)
    badges: list[str] = Field(default_factory=list)


class VLMDisclaimer(_VLMBase):
    text: str = ""
    time_ms: int = 0
    frame_index: int = 0
    is_small_print: bool = False


class VLMCreativeFormat(_VLMBase):
    aspect_ratio: str | None = None
    duration_ms: int = 0
    has_voiceover: bool = False
    has_on_screen_text: bool = False


class VLMMarketingEntities(_VLMBase):
    brand: VLMBrand = Field(default_factory=VLMBrand)
    products: list[str] = Field(default_factory=list)
    prices: list[VLMPrice] = Field(default_factory=list)
    offers: list[VLMOffer] = Field(default_factory=list)
    ctas: list[VLMCTA] = Field(default_factory=list)
    social_proof: VLMSocialProof = Field(default_factory=VLMSocialProof)
    disclaimers: list[VLMDisclaimer] = Field(default_factory=list)
    creative_format: VLMCreativeFormat = Field(default_factory=VLMCreativeFormat)


class VLMOCRError(_VLMBase):
    time_ms: int = 0
    frame_index: int = 0
    raw_ocr: str = ""
    corrected_text: str = ""
    confidence: float | None = None
    reason: str = ""


class VLMMissedText(_VLMBase):
    time_ms: int = 0
    frame_index: int = 0
    text: str = ""
    location: str | None = None
    confidence: float | None = None
    reason: str = ""


class VLMOCRQuality(_VLMBase):
    overall: OcrQualityLevel = "good"
    possible_errors: list[VLMOCRError] = Field(default_factory=list)
    missed_text: list[VLMMissedText] = Field(default_factory=list)


class VLMEvidence(_VLMBase):
    time_ms: int = 0
    frame_index: int = 0
    source: str = "vlm"
    text: str = ""
    reason: str = ""
    confidence: float | None = None


class VLMConflict(_VLMBase):
    description: str = ""
    sources: list[str] = Field(default_factory=list)
    resolution: str = ""


class VLMVerificationResult(_VLMBase):
    primary_category: str = "other"
    risk_labels: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    decision: Decision = "review"
    needs_human_review: bool = True
    ocr_quality: VLMOCRQuality = Field(default_factory=VLMOCRQuality)
    evidence: list[VLMEvidence] = Field(default_factory=list)
    marketing_entities: VLMMarketingEntities = Field(default_factory=VLMMarketingEntities)
    conflicts: list[VLMConflict] = Field(default_factory=list)
    summary: str = ""
    # Parsing metadata
    parse_ok: bool = True
    raw_response: str | None = None
    parse_error: str | None = None

    @classmethod
    def parse_failure(cls, raw_response: str, error: str) -> VLMVerificationResult:
        return cls(
            primary_category="other",
            confidence=0.0,
            decision="review",
            needs_human_review=True,
            summary=f"VLM response parsing failed: {error}",
            parse_ok=False,
            raw_response=raw_response,
            parse_error=error,
        )
