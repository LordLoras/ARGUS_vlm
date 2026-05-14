from __future__ import annotations

from typing import Any

from ad_classifier.campaigns.research_helpers import first_count, first_value
from ad_classifier.models.campaigns import CampaignRecord


def build_deep_research(
    campaign: CampaignRecord,
    detail: dict[str, Any],
    *,
    include_web: bool = False,
    question: str | None = None,
    thinking: bool = False,
) -> dict[str, Any]:
    research = detail["research"]
    ads = detail["ads"]
    summary = research["summary"]
    messaging = research["messaging"]
    creative = research["creative"]
    watchouts = research["watchouts"]
    findings = _deep_findings(summary, messaging, creative, watchouts, ads)
    assignment_review = _assignment_review(ads, summary)
    suggested_edits = _suggested_edits(campaign, messaging, findings)
    cleaned_question = question.strip() if question else None
    return {
        "mode": "local",
        "include_web": False,
        "web_available": False,
        "requested_web": include_web,
        "requested_question": cleaned_question,
        "analysis_mode": "local_structured_deep" if thinking else "local_structured",
        "scope": (
            "Local evidence only: campaign records, assigned ads, classifications, "
            "marketing entities, OCR/VLM-derived campaign suggestions, and assignment scores."
        ),
        "campaign": detail["campaign"],
        "generated_from": {
            "ad_count": len(ads),
            "ad_ids": [ad["ad_id"] for ad in ads if ad.get("ad_id")],
            "evidence_tables": [
                "campaigns",
                "ad_campaigns",
                "ads",
                "classifications",
                "marketing_entities",
            ],
        },
        "findings": findings,
        "creative_review": _creative_review(summary, messaging, creative),
        "assignment_review": assignment_review,
        "suggested_edits": suggested_edits,
        "question_answer": _question_answer(
            cleaned_question,
            findings,
            messaging,
            creative,
            watchouts,
            assignment_review,
            suggested_edits,
        ),
        "open_questions": _deep_questions(campaign.name, summary, messaging, watchouts),
        "future_expansion": {
            "web_research": "disabled",
            "supported_later": [
                "advertiser website checks",
                "landing-page offer comparison",
                "competitor/category scans",
                "current promotion validation",
            ],
        },
    }


def _deep_findings(
    summary: dict[str, Any],
    messaging: dict[str, Any],
    creative: dict[str, Any],
    watchouts: dict[str, Any],
    ads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    ad_count = int(summary["ad_count"] or 0)
    if ad_count == 0:
        return [
            {
                "priority": "high",
                "title": "Campaign has no assigned ads",
                "detail": "There is no local evidence to analyze until ads are assigned.",
                "evidence_ad_ids": [],
            }
        ]

    top_offer = first_count(messaging["top_offers"])
    if top_offer:
        findings.append(
            {
                "priority": "medium",
                "title": "Offer strategy is identifiable",
                "detail": f"{top_offer['value']} appears in {top_offer['count']} of {ad_count} assigned ads.",
                "evidence_ad_ids": _ads_with_value(ads, "offers", top_offer["value"]),
            }
        )

    top_cta = first_count(messaging["top_ctas"])
    if top_cta:
        findings.append(
            {
                "priority": "medium",
                "title": "CTA pattern is measurable",
                "detail": f"{top_cta['value']} is the most repeated call to action.",
                "evidence_ad_ids": _ads_with_value(ads, "ctas", top_cta["value"]),
            }
        )
    else:
        findings.append(
            {
                "priority": "high",
                "title": "CTA evidence is missing",
                "detail": "No extracted calls to action were found across the assigned ads.",
                "evidence_ad_ids": [ad["ad_id"] for ad in ads if ad.get("ad_id")],
            }
        )

    if len(messaging["top_products"]) >= 2:
        findings.append(
            {
                "priority": "low",
                "title": "Campaign has variant breadth",
                "detail": f"{len(messaging['top_products'])} product or SKU values appear in the local entities.",
                "evidence_ad_ids": [ad["ad_id"] for ad in ads if ad.get("products")],
            }
        )

    if watchouts["risk_labels"]:
        top_risk = first_count(watchouts["risk_labels"])
        findings.append(
            {
                "priority": "medium",
                "title": "Observation tags repeat",
                "detail": f"{top_risk['value']} appears in {top_risk['count']} assigned ads.",
                "evidence_ad_ids": _ads_with_value(ads, "risk_labels", top_risk["value"]),
            }
        )

    if int(creative["disclaimer_ads"]) > 0:
        findings.append(
            {
                "priority": "medium",
                "title": "Disclaimer burden needs review",
                "detail": (
                    f"{creative['disclaimer_ads']} ads include disclaimers; "
                    f"{creative['small_print_ads']} include small-print markers."
                ),
                "evidence_ad_ids": [
                    ad["ad_id"] for ad in ads if int(ad.get("disclaimer_count") or 0) > 0
                ],
            }
        )

    if watchouts["low_confidence_ads"]:
        findings.append(
            {
                "priority": "high",
                "title": "Some classifications need analyst review",
                "detail": "Low-confidence ads may weaken campaign-level conclusions.",
                "evidence_ad_ids": watchouts["low_confidence_ads"],
            }
        )

    return findings[:6]


def _creative_review(
    summary: dict[str, Any],
    messaging: dict[str, Any],
    creative: dict[str, Any],
) -> list[dict[str, Any]]:
    ad_count = max(int(summary["ad_count"] or 0), 1)
    top_brand = first_count(summary["brands"])
    top_cta = first_count(messaging["top_ctas"])
    top_format = first_count(creative["formats"])
    return [
        {
            "area": "Attention",
            "status": "review" if int(creative["on_screen_text_ads"]) >= ad_count else "unknown",
            "detail": (
                f"{creative['on_screen_text_ads']} ads have on-screen text signals; "
                "use frame evidence to check whether the hook is visually clear."
            ),
        },
        {
            "area": "Branding",
            "status": "present" if top_brand else "missing",
            "detail": (
                f"Dominant brand signal: {top_brand['value']} in {top_brand['count']} ads."
                if top_brand
                else "No consistent brand signal was extracted from assigned ads."
            ),
        },
        {
            "area": "Connection",
            "status": "present" if top_format or messaging["top_products"] else "unknown",
            "detail": (
                f"Creative format signal: {top_format['value']}."
                if top_format
                else "Review product/demo/story evidence manually; local structured signals are thin."
            ),
        },
        {
            "area": "Direction",
            "status": "present" if top_cta else "missing",
            "detail": (
                f"Primary CTA: {top_cta['value']} in {top_cta['count']} ads."
                if top_cta
                else "No repeated CTA was extracted."
            ),
        },
    ]


def _assignment_review(ads: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    primary_brand = first_count(summary["brands"])
    primary_category = first_count(summary["categories"])
    outliers: list[dict[str, Any]] = []
    for ad in ads:
        reasons: list[str] = []
        if ad.get("similarity_score") is not None and float(ad["similarity_score"]) < 0.72:
            reasons.append("low_similarity")
        if primary_brand and ad.get("brand_name") and ad["brand_name"] != primary_brand["value"]:
            reasons.append("brand_differs")
        if (
            primary_category
            and ad.get("primary_category")
            and ad["primary_category"] != primary_category["value"]
        ):
            reasons.append("category_differs")
        if reasons:
            outliers.append({"ad_id": ad.get("ad_id"), "reasons": reasons})

    return {
        "outliers": outliers,
        "missing_offer_ads": [ad.get("ad_id") for ad in ads if not ad.get("offers")],
        "missing_cta_ads": [ad.get("ad_id") for ad in ads if not ad.get("ctas")],
        "missing_product_ads": [ad.get("ad_id") for ad in ads if not ad.get("products")],
    }


def _suggested_edits(
    campaign: CampaignRecord,
    messaging: dict[str, Any],
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    signal = first_value(messaging["campaign_signals"])
    top_offer = first_count(messaging["top_offers"])
    products = [item["value"] for item in messaging["top_products"][:3]]
    if signal and signal != campaign.name:
        suggestions.append(
            {
                "field": "name",
                "value": signal,
                "reason": "Repeated local campaign-language signal differs from the current name.",
            }
        )
    if products and not campaign.theme:
        suggestions.append(
            {
                "field": "theme",
                "value": ", ".join(products),
                "reason": "Products are repeated enough to provide a concise campaign theme.",
            }
        )
    if top_offer and not campaign.description:
        suggestions.append(
            {
                "field": "description",
                "value": f"Local campaign group centered on {top_offer['value']}.",
                "reason": "Dominant offer can seed a human-editable description.",
            }
        )
    if findings and not suggestions:
        suggestions.append(
            {
                "field": "description",
                "value": findings[0]["detail"],
                "reason": "Top local finding can be used as a concise campaign note.",
            }
        )
    return suggestions[:3]


def _question_answer(
    question: str | None,
    findings: list[dict[str, Any]],
    messaging: dict[str, Any],
    creative: dict[str, Any],
    watchouts: dict[str, Any],
    assignment_review: dict[str, Any],
    suggested_edits: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not question:
        return None

    normalized = question.lower()
    evidence: list[str] = []
    if any(term in normalized for term in ("outlier", "belong", "cluster", "assignment")):
        outliers = assignment_review["outliers"]
        evidence = [item["ad_id"] for item in outliers if item.get("ad_id")]
        if outliers:
            answer = (
                f"{len(outliers)} assigned ads need membership review. "
                "The report flags low similarity, brand differences, or category differences."
            )
        else:
            answer = "No local assignment outliers were detected from similarity, brand, or category signals."
    elif any(term in normalized for term in ("improve", "optimize", "edit", "change")):
        if suggested_edits:
            edits = "; ".join(
                f"{item['field']} -> {item['value']}" for item in suggested_edits[:3]
            )
            answer = f"Recommended campaign edits from local evidence: {edits}."
        else:
            answer = "Local evidence does not support a specific campaign metadata edit yet."
        evidence = _finding_ad_ids(findings)
    elif any(term in normalized for term in ("offer", "price", "cta", "message")):
        offer = first_count(messaging["top_offers"])
        cta = first_count(messaging["top_ctas"])
        answer = (
            f"Top offer: {offer['value']} ({offer['count']} ads). "
            if offer
            else "No repeated offer was extracted. "
        )
        answer += (
            f"Top CTA: {cta['value']} ({cta['count']} ads)."
            if cta
            else "No repeated CTA was extracted."
        )
        evidence = _finding_ad_ids(findings)
    elif any(term in normalized for term in ("fine", "disclaimer", "small print", "text heavy")):
        answer = (
            f"{creative['disclaimer_ads']} ads include disclaimers, "
            f"{creative['small_print_ads']} include small-print markers, and "
            f"{watchouts['small_print_count']} disclaimer items were classified as small print."
        )
        evidence = _finding_ad_ids(findings)
    else:
        lead = findings[0]["detail"] if findings else "No strong campaign-level finding was generated."
        answer = f"Best local answer: {lead}"
        evidence = _finding_ad_ids(findings[:1])

    return {
        "question": question,
        "answer": answer,
        "evidence_ad_ids": evidence,
        "limits": "Local-only answer; no web, landing page, or competitor evidence was used.",
    }


def _deep_questions(
    campaign_name: str,
    summary: dict[str, Any],
    messaging: dict[str, Any],
    watchouts: dict[str, Any],
) -> list[str]:
    questions = [
        f"Which assigned ads best represent {campaign_name}, and which look like outliers?",
        f"What should change in {campaign_name}'s offer, CTA, or product emphasis?",
    ]
    if messaging["top_products"]:
        questions.append("Do product variants map to clearly different creative treatments?")
    if watchouts["risk_labels"]:
        questions.append("Which observation tags are strategic tactics versus extraction noise?")
    if not summary["brands"] or not messaging["top_ctas"]:
        questions.append("What metadata must be corrected before this campaign is demo-ready?")
    return questions[:5]


def _ads_with_value(ads: list[dict[str, Any]], key: str, value: Any) -> list[str]:
    return [
        ad["ad_id"]
        for ad in ads
        if ad.get("ad_id") and str(value) in {str(item) for item in ad.get(key, [])}
    ]


def _finding_ad_ids(findings: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for finding in findings:
        for ad_id in finding.get("evidence_ad_ids", []):
            if ad_id and ad_id not in seen:
                seen.add(ad_id)
                ids.append(ad_id)
    return ids
