from __future__ import annotations

from typing import Any

from ad_classifier.agent.client import AgentClient
from ad_classifier.campaigns.research_agent import (
    answer_campaign_question,
    generate_campaign_research_report,
)
from ad_classifier.campaigns.research_helpers import first_count, first_value
from ad_classifier.models.campaigns import CampaignRecord


def build_deep_research(
    campaign: CampaignRecord,
    detail: dict[str, Any],
    *,
    include_web: bool = False,
    question: str | None = None,
    thinking: bool = False,
    client: AgentClient | None = None,
) -> dict[str, Any]:
    research = detail["research"]
    ads = detail["ads"]
    summary = research["summary"]
    messaging = research["messaging"]
    creative = research["creative"]
    watchouts = research["watchouts"]
    findings = _deep_findings(summary, messaging, creative, watchouts, ads)
    creative_review = _creative_review(summary, messaging, creative)
    assignment_review = _assignment_review(ads, summary)
    suggested_edits = _suggested_edits(campaign, messaging, findings)
    open_questions = _deep_questions(campaign.name, summary, messaging, watchouts)
    cleaned_question = question.strip() if question else None
    agent_report = generate_campaign_research_report(
        client=client,
        question=cleaned_question,
        detail=detail,
        findings=findings,
        creative_review=creative_review,
        assignment_review=assignment_review,
        suggested_edits=suggested_edits,
        open_questions=open_questions,
        thinking=thinking,
    )
    research_source = "llm" if agent_report and agent_report.get("source") == "llm" else "local"
    if research_source == "llm":
        findings = agent_report.get("findings") or findings
        creative_review = agent_report.get("creative_review") or creative_review
        suggested_edits = agent_report.get("suggested_edits") or suggested_edits
        open_questions = agent_report.get("open_questions") or open_questions
        question_answer = agent_report.get("question_answer")
        if cleaned_question and not question_answer:
            question_answer = answer_campaign_question(
                client=None,
                question=cleaned_question,
                detail=detail,
                findings=findings,
                creative_review=creative_review,
                assignment_review=assignment_review,
                suggested_edits=suggested_edits,
                thinking=thinking,
            )
            if question_answer:
                question_answer["source"] = "local_fallback"
    else:
        question_answer = answer_campaign_question(
            client=None,
            question=cleaned_question,
            detail=detail,
            findings=findings,
            creative_review=creative_review,
            assignment_review=assignment_review,
            suggested_edits=suggested_edits,
            thinking=thinking,
        )
        if question_answer and agent_report:
            question_answer["source"] = "local_fallback"
            if agent_report.get("finish_reason"):
                question_answer["finish_reason"] = agent_report["finish_reason"]
            if agent_report.get("error"):
                question_answer["error"] = agent_report["error"]

    return {
        "mode": "local",
        "include_web": False,
        "web_available": False,
        "requested_web": include_web,
        "requested_question": cleaned_question,
        "analysis_mode": "agent_deep_research" if research_source == "llm" else "local_structured",
        "research_source": research_source,
        "scope": (
            "Local evidence only: campaign records, assigned ads, classifications, "
            "marketing entities, OCR/GLM-OCR/VLM evidence, and assignment scores."
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
                "frames",
                "ocr_items",
                "transcript_segments",
            ],
        },
        "findings": findings,
        "creative_review": creative_review,
        "assignment_review": assignment_review,
        "suggested_edits": suggested_edits,
        "question_answer": question_answer,
        "open_questions": open_questions,
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
