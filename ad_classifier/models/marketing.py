from __future__ import annotations

from typing import Literal

from pydantic import Field

from ad_classifier.models.common import EvidenceItem, StrictModel

AspectRatio = Literal["1:1", "9:16", "16:9", "4:5", "4:3"]
PhoneNumberType = Literal["phone", "sms", "vanity", "fax", "other"]
SocialPlatform = Literal[
    "facebook",
    "instagram",
    "tiktok",
    "youtube",
    "x",
    "linkedin",
    "pinterest",
    "snapchat",
    "other",
]
AppStorePlatform = Literal["ios", "android", "amazon", "windows", "other"]
CreativeFormatType = Literal[
    "product_demo",
    "testimonial",
    "service_explainer",
    "offer_end_card",
    "ugc_style",
    "app_walkthrough",
    "before_after",
    "brand_spot",
    "other",
]
DisclaimerDensity = Literal["none", "low", "medium", "high"]


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
    is_small_print: bool = False


class CreativeFormat(StrictModel):
    aspect_ratio: AspectRatio | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    has_voiceover: bool = False
    has_on_screen_text: bool = False


class WebsiteEntity(StrictModel):
    url: str
    domain: str | None = None
    display_text: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class PhoneNumberEntity(StrictModel):
    raw: str
    normalized: str | None = None
    type: PhoneNumberType = "phone"
    evidence: list[EvidenceItem] = Field(default_factory=list)


class SocialHandleEntity(StrictModel):
    platform: SocialPlatform = "other"
    handle: str | None = None
    url: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class AppStoreLinkEntity(StrictModel):
    platform: AppStorePlatform = "other"
    url: str
    app_name: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class QRCodeEntity(StrictModel):
    present: bool = False
    decoded_text: str | None = None
    destination_hint: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ContactPoints(StrictModel):
    websites: list[WebsiteEntity] = Field(default_factory=list)
    phone_numbers: list[PhoneNumberEntity] = Field(default_factory=list)
    social_handles: list[SocialHandleEntity] = Field(default_factory=list)
    app_store_links: list[AppStoreLinkEntity] = Field(default_factory=list)
    qr_codes: list[QRCodeEntity] = Field(default_factory=list)


class AdvertiserEntity(StrictModel):
    advertiser_name: str | None = None
    brand_name: str | None = None
    parent_company: str | None = None
    service_area: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class LandingPageEntity(StrictModel):
    url: str | None = None
    domain: str | None = None
    path: str | None = None
    utm_params: dict[str, str] = Field(default_factory=dict)
    final_url: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class PromoCodeEntity(StrictModel):
    code: str
    raw_text: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ExpiryEntity(StrictModel):
    text: str | None = None
    resolved_date: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class FinancingTerms(StrictModel):
    text: str | None = None
    apr: float | None = Field(default=None, ge=0)
    monthly_payment: float | None = Field(default=None, ge=0)
    currency: str | None = None
    duration_months: int | None = Field(default=None, ge=0)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class OfferTerms(StrictModel):
    promo_codes: list[PromoCodeEntity] = Field(default_factory=list)
    expiry: ExpiryEntity = Field(default_factory=ExpiryEntity)
    financing: FinancingTerms = Field(default_factory=FinancingTerms)
    trial_terms: list[str] = Field(default_factory=list)
    guarantees: list[str] = Field(default_factory=list)
    scarcity_signals: list[str] = Field(default_factory=list)
    urgency_signals: list[str] = Field(default_factory=list)


class CreativeAttributes(StrictModel):
    format: CreativeFormatType | None = None
    aspect_ratio: AspectRatio | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    voiceover: bool = False
    music: bool = False
    testimonial: bool = False
    before_after: bool = False
    demo: bool = False
    ugc_style: bool = False
    end_card: bool = False
    disclaimer_density: DisclaimerDensity = "none"


class CampaignSuggestion(StrictModel):
    name: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class MarketingEntities(StrictModel):
    brand: BrandEntity = Field(default_factory=BrandEntity)
    subcategory: str | None = None
    products: list[str] = Field(default_factory=list)
    prices: list[PriceEntity] = Field(default_factory=list)
    offers: list[OfferEntity] = Field(default_factory=list)
    ctas: list[CTAEntity] = Field(default_factory=list)
    social_proof: SocialProof = Field(default_factory=SocialProof)
    disclaimers: list[DisclaimerEntity] = Field(default_factory=list)
    creative_format: CreativeFormat = Field(default_factory=CreativeFormat)
    contact_points: ContactPoints = Field(default_factory=ContactPoints)
    advertiser: AdvertiserEntity = Field(default_factory=AdvertiserEntity)
    landing_page: LandingPageEntity = Field(default_factory=LandingPageEntity)
    offer_terms: OfferTerms = Field(default_factory=OfferTerms)
    creative_attributes: CreativeAttributes = Field(default_factory=CreativeAttributes)
    campaign_suggestions: list[CampaignSuggestion] = Field(default_factory=list)

    @property
    def products_text(self) -> str | None:
        return ", ".join(self.products) if self.products else None

    @property
    def primary_website_domain(self) -> str | None:
        if self.contact_points.websites:
            return self.contact_points.websites[0].domain
        return self.landing_page.domain

    @property
    def primary_phone_number(self) -> str | None:
        if not self.contact_points.phone_numbers:
            return None
        phone = self.contact_points.phone_numbers[0]
        return phone.normalized or phone.raw
