from __future__ import annotations

from typing import Literal

from pydantic import Field

from ad_classifier.models.common import EvidenceItem, StrictModel

AspectRatio = Literal["1:1", "9:16", "16:9", "4:5"]


class BrandEntity(StrictModel):
    name: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    logo_present: bool = False
    logo_evidence: list[EvidenceItem] = Field(default_factory=list)
    tagline: str | None = None


class PriceEntity(StrictModel):
    text: str
    amount: float | None = None
    currency: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class OfferEntity(StrictModel):
    text: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class CTAEntity(StrictModel):
    text: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class SocialProof(StrictModel):
    rating: float | None = None
    rating_count: int | None = Field(default=None, ge=0)
    testimonials: list[str] = Field(default_factory=list)
    badges: list[str] = Field(default_factory=list)


class DisclaimerEntity(StrictModel):
    text: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class CreativeFormat(StrictModel):
    aspect_ratio: AspectRatio | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    has_voiceover: bool = False
    has_on_screen_text: bool = False


class MarketingEntities(StrictModel):
    brand: BrandEntity = Field(default_factory=BrandEntity)
    products: list[str] = Field(default_factory=list)
    prices: list[PriceEntity] = Field(default_factory=list)
    offers: list[OfferEntity] = Field(default_factory=list)
    ctas: list[CTAEntity] = Field(default_factory=list)
    social_proof: SocialProof = Field(default_factory=SocialProof)
    disclaimers: list[DisclaimerEntity] = Field(default_factory=list)
    creative_format: CreativeFormat = Field(default_factory=CreativeFormat)

    @property
    def products_text(self) -> str | None:
        return ", ".join(self.products) if self.products else None
