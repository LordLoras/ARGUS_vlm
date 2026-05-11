from __future__ import annotations

import re

from ad_classifier.marketing.brand import brand_normalize
from ad_classifier.models.classification import Decision
from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import (
    AdvertiserEntity,
    AppStoreLinkEntity,
    BrandEntity,
    CampaignSuggestion,
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


def _map_vlm_evidence(vlm: VLMVerificationResult) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for e in vlm.evidence:
        items.append(
            EvidenceItem(
                time_ms=e.time_ms,
                frame_index=e.frame_index,
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
                frame_index=item.frame_index,
                source="vlm",
                text=text,
                confidence=item.confidence,
                reason=item.reason or None,
            )
        )
    return evidence


def _rule_evidence(rules: list[RuleTrigger]) -> list[EvidenceItem]:
    deduped: dict[str, RuleTrigger] = {}
    order: list[str] = []
    for rule in rules:
        text = _normalize_rule_evidence_text(rule.evidence_text or rule.rule_id)
        compact = _compact_evidence_key(text)
        matched_key = None
        for existing_key in order:
            if _fuzzy_evidence_match(compact, existing_key):
                matched_key = existing_key
                break
        if matched_key is None:
            deduped[compact] = rule.model_copy(update={"evidence_text": text})
            order.append(compact)
        else:
            current = deduped[matched_key]
            if _rule_evidence_score(rule) > _rule_evidence_score(current):
                deduped[matched_key] = rule.model_copy(update={"evidence_text": text})

    items: list[EvidenceItem] = []
    for key in order:
        r = deduped[key]
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


def _fuzzy_evidence_match(a: str, b: str) -> bool:
    if not a or not b:
        return a == b
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    shared = sum(1 for c in shorter if c in longer)
    ratio = shared / max(len(longer), 1)
    if ratio < 0.6:
        return False
    if len(shorter) < 20 and abs(len(a) - len(b)) > max(len(a), len(b)) * 0.5:
        return False
    return True


def _normalize_rule_evidence_text(text: str) -> str:
    text = text.replace("％", "%")
    text = re.sub(r"\bONSELECT\b", "ON SELECT", text, flags=re.IGNORECASE)
    text = re.sub(r"\bOffersexclude\b", "Offers exclude", text, flags=re.IGNORECASE)
    text = re.sub(r"\bAPRfinancing\b", "APR financing", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=[a-zA-Z])(?=\$)", " ", text)
    text = re.sub(r"(?<=\d)(?=\$)", " ", text)
    text = re.sub(r"(?<=[a-z])\.(?=[A-Z0-9])", ". ", text)
    text = re.sub(r"(?<=\d)\.(?=[A-Z])", ". ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact_evidence_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _rule_evidence_score(rule: RuleTrigger) -> int:
    text = _normalize_rule_evidence_text(rule.evidence_text or rule.rule_id)
    return len(text) + text.count(" ") * 2 + text.count(". ") * 3


def _currency_symbol(currency: str | None) -> str:
    normalized = (currency or "$").strip().upper()
    if normalized in {"USD", "US$", "$"}:
        return "$"
    return currency or "$"


def _format_amount(amount: float) -> str:
    if float(amount).is_integer():
        return f"{int(amount):,}"
    return f"{amount:,.2f}".rstrip("0").rstrip(".")


def _format_price(currency: str | None, amount: float) -> str:
    return f"{_currency_symbol(currency)}{_format_amount(amount)}"


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
                frame_index=le.frame_index,
                source="vlm",
                text=le.reason,
            )
            for le in me.brand.logo_evidence
        ],
    )

    prices = [
        PriceEntity(
            text=_format_price(p.currency, p.amount),
            amount=p.amount if p.amount else None,
            currency=_currency_symbol(p.currency),
            evidence=[
                EvidenceItem(
                    time_ms=p.time_ms,
                    frame_index=p.frame_index,
                    source="vlm",
                    text=_format_price(p.currency, p.amount),
                )
            ],
        )
        for p in me.prices
        if p.amount > 0
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
                    frame_index=c.frame_index,
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
                    frame_index=d.frame_index,
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

    campaign_suggestions = [
        CampaignSuggestion(
            name=s.name,
            confidence=s.confidence,
            evidence=_entity_evidence(s.evidence),
        )
        for s in me.campaign_suggestions
        if s.name
    ]

    return MarketingEntities(
        brand=brand,
        subcategory=me.subcategory or None,
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
        campaign_suggestions=campaign_suggestions,
    )


def _parse_rating_count(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else None


def _decide(
    vlm_decision: Decision,
    vlm_confidence: float,
    has_rule_triggers: bool,
    config: AggregationConfig,
) -> tuple[Decision, bool]:
    if vlm_decision == "allow" and vlm_confidence >= config.allow_threshold and not has_rule_triggers:
        return "allow", False

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

    has_rules = len(rules_triggered) > 0

    decision, needs_review = _decide(
        vlm_result.decision,
        vlm_result.confidence,
        has_rules,
        cfg,
    )

    evidence = _map_vlm_evidence(vlm_result) + _rule_evidence(rules_triggered)

    marketing_entities = _map_marketing_entities(vlm_result)

    return FinalAdClassification(
        ad_id=ad_id,
        primary_category=vlm_result.primary_category or "other",
        risk_labels=[],
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
