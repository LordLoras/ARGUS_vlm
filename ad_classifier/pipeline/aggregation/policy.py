from __future__ import annotations

from pathlib import Path

import yaml

from ad_classifier.marketing.brand import brand_normalize
from ad_classifier.models.classification import Decision
from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import (
    AdvertiserEntity,
    AppStoreLinkEntity,
    BrandEntity,
    CampaignSignals,
    ContactPoints,
    CreativeAttributes,
    CreativeFormat,
    CTAEntity,
    DisclaimerEntity,
    ExpiryEntity,
    FinancingTerms,
    LandingPageEntity,
    MarketingEntities,
    OfferEntity,
    OfferTerms,
    PhoneNumberEntity,
    PriceEntity,
    PromoCodeEntity,
    QRCodeEntity,
    SocialHandleEntity,
    SocialProof,
    WebsiteEntity,
)
from ad_classifier.pipeline.aggregation.models import (
    AggregationConfig,
    FinalAdClassification,
    RelatedAds,
)
from ad_classifier.pipeline.rules.models import RuleTrigger
from ad_classifier.vlm.models import VLMVerificationResult

_TAXONOMY_PATH = Path(__file__).parent.parent.parent.parent / "taxonomy.yaml"


def _sensitive_categories() -> set[str]:
    try:
        data = yaml.safe_load(_TAXONOMY_PATH.read_text(encoding="utf-8")) or {}
        return {c["id"] for c in data.get("categories", []) if c.get("sensitive", False)}
    except Exception:
        return set()


def _map_vlm_evidence(vlm: VLMVerificationResult) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for e in vlm.evidence:
        items.append(
            EvidenceItem(
                time_ms=e.time_ms,
                frame_index=e.frame_index if e.frame_index != 0 else None,
                source="vlm",
                text=e.text,
                confidence=e.confidence,
                reason=e.reason or None,
            )
        )
    return items


def _entity_evidence(items) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for item in items:
        text = item.text or item.reason
        if not text:
            continue
        evidence.append(
            EvidenceItem(
                time_ms=item.time_ms,
                frame_index=item.frame_index if item.frame_index != 0 else None,
                source="vlm",
                text=text,
                confidence=item.confidence,
                reason=item.reason or None,
            )
        )
    return evidence


def _rule_evidence(rules: list[RuleTrigger]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for r in rules:
        items.append(
            EvidenceItem(
                time_ms=r.time_ms or 0,
                frame_index=r.frame_index,
                source="rule",
                text=r.evidence_text or r.rule_id,
                reason=f"rule={r.rule_id} severity={r.severity}",
            )
        )
    return items


def _map_marketing_entities(vlm: VLMVerificationResult) -> MarketingEntities:
    me = vlm.marketing_entities
    brand_name = brand_normalize(me.brand.name)

    brand = BrandEntity(
        name=brand_name,
        logo_present=me.brand.logo_present,
        tagline=me.brand.tagline,
        logo_evidence=[
            EvidenceItem(
                time_ms=le.time_ms,
                frame_index=le.frame_index if le.frame_index != 0 else None,
                source="vlm",
                text=le.reason,
            )
            for le in me.brand.logo_evidence
        ],
    )

    prices = [
        PriceEntity(
            text=f"{p.currency or ''}{p.amount}" if p.amount else "",
            amount=p.amount if p.amount else None,
            currency=p.currency or None,
            evidence=[
                EvidenceItem(
                    time_ms=p.time_ms,
                    frame_index=p.frame_index if p.frame_index != 0 else None,
                    source="vlm",
                    text=f"{p.currency}{p.amount}",
                )
            ],
        )
        for p in me.prices
    ]

    offers = [
        OfferEntity(
            text=o.value or o.type,
            evidence=[],
        )
        for o in me.offers
    ]

    ctas = [
        CTAEntity(
            text=c.text,
            evidence=[
                EvidenceItem(
                    time_ms=c.time_ms,
                    frame_index=c.frame_index if c.frame_index != 0 else None,
                    source="vlm",
                    text=c.text,
                )
            ],
        )
        for c in me.ctas
    ]

    disclaimers = [
        DisclaimerEntity(
            text=d.text,
            evidence=[
                EvidenceItem(
                    time_ms=d.time_ms,
                    frame_index=d.frame_index if d.frame_index != 0 else None,
                    source="vlm",
                    text=d.text,
                )
            ],
        )
        for d in me.disclaimers
    ]

    social_proof = SocialProof(
        rating=me.social_proof.rating,
        rating_count=_parse_rating_count(me.social_proof.rating_count),
        testimonials=list(me.social_proof.testimonials),
        badges=list(me.social_proof.badges),
    )

    cf_vlm = me.creative_format
    creative_format = CreativeFormat(
        aspect_ratio=cf_vlm.aspect_ratio or None,
        duration_ms=cf_vlm.duration_ms if cf_vlm.duration_ms > 0 else None,
        has_voiceover=cf_vlm.has_voiceover,
        has_on_screen_text=cf_vlm.has_on_screen_text,
    )

    contact_points = ContactPoints(
        websites=[
            WebsiteEntity(
                url=w.url,
                domain=w.domain,
                display_text=w.display_text,
                evidence=_entity_evidence(w.evidence),
            )
            for w in me.contact_points.websites
            if w.url
        ],
        phone_numbers=[
            PhoneNumberEntity(
                raw=p.raw,
                normalized=p.normalized,
                type=p.type,
                evidence=_entity_evidence(p.evidence),
            )
            for p in me.contact_points.phone_numbers
            if p.raw
        ],
        social_handles=[
            SocialHandleEntity(
                platform=s.platform,
                handle=s.handle,
                url=s.url,
                evidence=_entity_evidence(s.evidence),
            )
            for s in me.contact_points.social_handles
            if s.handle or s.url
        ],
        app_store_links=[
            AppStoreLinkEntity(
                platform=a.platform,
                url=a.url,
                app_name=a.app_name,
                evidence=_entity_evidence(a.evidence),
            )
            for a in me.contact_points.app_store_links
            if a.url
        ],
        qr_codes=[
            QRCodeEntity(
                present=q.present,
                decoded_text=q.decoded_text,
                destination_hint=q.destination_hint,
                evidence=_entity_evidence(q.evidence),
            )
            for q in me.contact_points.qr_codes
            if q.present or q.decoded_text or q.destination_hint
        ],
    )

    advertiser = AdvertiserEntity(
        advertiser_name=me.advertiser.advertiser_name,
        brand_name=brand_normalize(me.advertiser.brand_name),
        parent_company=me.advertiser.parent_company,
        service_area=list(me.advertiser.service_area),
        locations=list(me.advertiser.locations),
        evidence=_entity_evidence(me.advertiser.evidence),
    )

    landing_page = LandingPageEntity(
        url=me.landing_page.url,
        domain=me.landing_page.domain,
        path=me.landing_page.path,
        utm_params=dict(me.landing_page.utm_params),
        final_url=me.landing_page.final_url,
        evidence=_entity_evidence(me.landing_page.evidence),
    )

    offer_terms = OfferTerms(
        promo_codes=[
            PromoCodeEntity(
                code=p.code,
                raw_text=p.raw_text,
                evidence=_entity_evidence(p.evidence),
            )
            for p in me.offer_terms.promo_codes
            if p.code
        ],
        expiry=ExpiryEntity(
            text=me.offer_terms.expiry.text,
            resolved_date=me.offer_terms.expiry.resolved_date,
            evidence=_entity_evidence(me.offer_terms.expiry.evidence),
        ),
        financing=FinancingTerms(
            text=me.offer_terms.financing.text,
            apr=me.offer_terms.financing.apr,
            monthly_payment=me.offer_terms.financing.monthly_payment,
            currency=me.offer_terms.financing.currency,
            duration_months=me.offer_terms.financing.duration_months,
            evidence=_entity_evidence(me.offer_terms.financing.evidence),
        ),
        trial_terms=list(me.offer_terms.trial_terms),
        guarantees=list(me.offer_terms.guarantees),
        scarcity_signals=list(me.offer_terms.scarcity_signals),
        urgency_signals=list(me.offer_terms.urgency_signals),
    )

    creative_attributes = CreativeAttributes(
        format=me.creative_attributes.format,
        aspect_ratio=me.creative_attributes.aspect_ratio or creative_format.aspect_ratio,
        duration_ms=me.creative_attributes.duration_ms or creative_format.duration_ms,
        voiceover=me.creative_attributes.voiceover or creative_format.has_voiceover,
        music=me.creative_attributes.music,
        testimonial=me.creative_attributes.testimonial,
        before_after=me.creative_attributes.before_after,
        demo=me.creative_attributes.demo,
        ugc_style=me.creative_attributes.ugc_style,
        end_card=me.creative_attributes.end_card,
        disclaimer_density=me.creative_attributes.disclaimer_density,
    )

    campaign_signals = CampaignSignals(
        slogan=me.campaign_signals.slogan,
        recurring_offer=me.campaign_signals.recurring_offer,
        product_model=me.campaign_signals.product_model,
        sku=me.campaign_signals.sku,
        creative_variant=me.campaign_signals.creative_variant,
        campaign_theme=me.campaign_signals.campaign_theme,
        evidence=_entity_evidence(me.campaign_signals.evidence),
    )

    return MarketingEntities(
        brand=brand,
        products=list(me.products),
        prices=prices,
        offers=offers,
        ctas=ctas,
        social_proof=social_proof,
        disclaimers=disclaimers,
        creative_format=creative_format,
        contact_points=contact_points,
        advertiser=advertiser,
        landing_page=landing_page,
        offer_terms=offer_terms,
        creative_attributes=creative_attributes,
        campaign_signals=campaign_signals,
    )


def _parse_rating_count(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else None


def _decide(
    vlm_decision: Decision,
    vlm_confidence: float,
    primary_category: str,
    rule_risk_labels: list[str],
    config: AggregationConfig,
) -> tuple[Decision, bool]:
    sensitive = _sensitive_categories()
    is_sensitive = primary_category in sensitive

    threshold = config.sensitive_review_threshold if is_sensitive else config.allow_threshold

    # Strong flag: VLM says flag with high confidence
    if vlm_decision == "flag" and vlm_confidence >= config.flag_threshold:
        return "flag", True

    # Rule engine found risk labels → at minimum review
    if rule_risk_labels:
        if vlm_decision == "allow" and vlm_confidence >= config.flag_threshold and not is_sensitive:
            return "review", True
        return "flag" if vlm_decision == "flag" else "review", True

    # VLM says allow with sufficient confidence
    if vlm_decision == "allow" and vlm_confidence >= threshold:
        return "allow", False

    # VLM says review or confidence is below threshold
    return "review", True


def aggregate(
    ad_id: str,
    vlm_result: VLMVerificationResult,
    rules_triggered: list[RuleTrigger],
    *,
    config: AggregationConfig | None = None,
    related_ads: RelatedAds | None = None,
    vlm_model: str = "",
    vlm_prompt_version: str = "",
    pipeline_version: str = "",
) -> FinalAdClassification:
    cfg = config or AggregationConfig()

    rule_risk_labels = [r.risk_label for r in rules_triggered if r.risk_label]

    combined_risk_labels = list(dict.fromkeys(vlm_result.risk_labels + rule_risk_labels))

    decision, needs_review = _decide(
        vlm_result.decision,
        vlm_result.confidence,
        vlm_result.primary_category,
        rule_risk_labels,
        cfg,
    )

    evidence = _map_vlm_evidence(vlm_result) + _rule_evidence(rules_triggered)

    marketing_entities = _map_marketing_entities(vlm_result)

    return FinalAdClassification(
        ad_id=ad_id,
        primary_category=vlm_result.primary_category or "other",
        risk_labels=combined_risk_labels,
        confidence=vlm_result.confidence,
        decision=decision,
        needs_human_review=needs_review,
        evidence=evidence,
        marketing_entities=marketing_entities,
        related_ads=related_ads or RelatedAds(),
        vlm_model=vlm_model,
        vlm_prompt_version=vlm_prompt_version,
        pipeline_version=pipeline_version,
    )
