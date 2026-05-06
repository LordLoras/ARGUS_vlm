from __future__ import annotations

import yaml
from pathlib import Path

from ad_classifier.marketing.brand import brand_normalize
from ad_classifier.models.classification import Decision
from ad_classifier.models.common import EvidenceItem
from ad_classifier.models.marketing import (
    BrandEntity,
    CTAEntity,
    CreativeFormat,
    DisclaimerEntity,
    MarketingEntities,
    OfferEntity,
    PriceEntity,
    SocialProof,
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

    return MarketingEntities(
        brand=brand,
        products=list(me.products),
        prices=prices,
        offers=offers,
        ctas=ctas,
        social_proof=social_proof,
        disclaimers=disclaimers,
        creative_format=creative_format,
    )


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
