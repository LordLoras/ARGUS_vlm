from __future__ import annotations

import json
import re
from typing import Any

from ad_classifier.agent.client import AgentClient, AgentClientError
from ad_classifier.campaigns.research_agent_parse import parse_research_report
from ad_classifier.campaigns.research_helpers import first_count


def generate_campaign_research_report(
    *,
    client: AgentClient | None,
    question: str | None,
    detail: dict[str, Any],
    findings: list[dict[str, Any]],
    creative_review: list[dict[str, Any]],
    assignment_review: dict[str, Any],
    suggested_edits: list[dict[str, Any]],
    open_questions: list[str],
    thinking: bool = False,
) -> dict[str, Any] | None:
    if client is None:
        return None

    evidence = _context_payload(
        detail,
        findings,
        creative_review,
        assignment_review,
        suggested_edits,
        open_questions,
    )
    messages = [
        {"role": "system", "content": _REPORT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Analyst question: {question or ''}\n\n"
                "Local campaign evidence JSON:\n"
                f"{json.dumps(evidence, ensure_ascii=True)}"
            ),
        },
    ]
    try:
        response = client.complete(messages, enable_thinking=thinking)
        raw = (response.content or "").strip()
        if not raw and response.finish_reason == "length" and thinking:
            response = client.complete(messages, enable_thinking=False)
            raw = (response.content or "").strip()
    except AgentClientError as exc:
        return {"source": "local_fallback", "error": str(exc)[:240]}

    report = parse_research_report(
        raw,
        finish_reason=response.finish_reason,
        question=question,
        detail=detail,
    )
    if not report:
        return {
            "source": "local_fallback",
            "finish_reason": response.finish_reason,
            "error": "agent returned non-json research report",
        }
    return report


def answer_campaign_question(
    *,
    client: AgentClient | None,
    question: str | None,
    detail: dict[str, Any],
    findings: list[dict[str, Any]],
    creative_review: list[dict[str, Any]],
    assignment_review: dict[str, Any],
    suggested_edits: list[dict[str, Any]],
    thinking: bool = False,
) -> dict[str, Any] | None:
    if not question:
        return None
    if client is None:
        return _local_question_answer(question, detail, findings, assignment_review, suggested_edits)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                "Local campaign evidence JSON:\n"
                f"{json.dumps(_context_payload(detail, findings, creative_review, assignment_review, suggested_edits, []), ensure_ascii=True)}"
            ),
        },
    ]
    try:
        response = client.complete(messages, enable_thinking=thinking)
        answer = (response.content or "").strip()
        if not answer and response.finish_reason == "length" and thinking:
            response = client.complete(messages, enable_thinking=False)
    except AgentClientError as exc:
        fallback = _local_question_answer(
            question,
            detail,
            findings,
            assignment_review,
            suggested_edits,
        )
        fallback["source"] = "local_fallback"
        fallback["error"] = str(exc)[:240]
        return fallback

    answer = (response.content or "").strip()
    if not answer:
        fallback = _local_question_answer(
            question,
            detail,
            findings,
            assignment_review,
            suggested_edits,
        )
        fallback["source"] = "local_fallback"
        fallback["finish_reason"] = response.finish_reason
        return fallback

    return {
        "question": question,
        "answer": answer,
        "evidence_ad_ids": _mentioned_ad_ids(answer, detail) or _finding_ad_ids(findings),
        "limits": "LLM answer grounded only in local campaign evidence; no web, landing page, or competitor data was used.",
        "source": "llm",
        "finish_reason": response.finish_reason,
    }


_SYSTEM_PROMPT = """You are ARGUS, a campaign research analyst for a local ad database.
Answer using only the provided local campaign evidence JSON.
If the user's wording is slightly incomplete, infer the likely campaign-analysis intent when the question mentions this campaign, ads, products, offers, CTAs, creative, or evidence.
If the question asks how products are related, compare product names, brand, category, offers, CTAs, and assigned ad context. Say whether they look like variants/SKUs in one campaign, related products in a broader lineup, unrelated products, or insufficient evidence.
If the question is not about this campaign, its ads, products, offers, CTAs, creative, evidence quality, or marketing implications, say it is outside this campaign research scope and suggest a campaign-specific question.
Do not answer general knowledge, philosophy, medical, legal, or web-current questions.
Do not invent products, counts, campaign names, or ad_ids. Cite ad_ids when making record-specific claims.
Keep the answer under 160 words unless the user asks for detail."""


_REPORT_SYSTEM_PROMPT = """You are ARGUS, a senior campaign research analyst for a local ad database.
You receive local evidence only: campaign assignments, key metrics, marketing entities, OCR/GLM-OCR excerpts, transcript excerpts, VLM classification evidence, and deterministic metric signals.
Generate the visible deep-research report from those metrics and evidence. Do not merely restate every metric; infer the marketing meaning.
No internet, competitor, landing-page, or current-market claims unless they are in the evidence.
If the analyst question is off-topic, keep question_answer scoped to campaign research.
Return one strict JSON object and no markdown:
{
  "findings": [{"priority":"high|medium|low","title":"...","detail":"...","evidence_ad_ids":["ad_id"]}],
  "creative_review": [{"area":"Attention|Branding|Connection|Direction","status":"present|review|missing|unknown","detail":"..."}],
  "suggested_edits": [{"field":"name|theme|description|assignments|notes","value":"...","reason":"..."}],
  "open_questions": ["..."],
  "question_answer": {"question":"...","answer":"...","evidence_ad_ids":["ad_id"],"limits":"..."} | null
}
Keep findings to 3-5 items, prioritize commercial strategy, offer/CTA clarity, product architecture, evidence quality, and assignment outliers. Cite real ad_ids only."""


def _context_payload(
    detail: dict[str, Any],
    findings: list[dict[str, Any]],
    creative_review: list[dict[str, Any]],
    assignment_review: dict[str, Any],
    suggested_edits: list[dict[str, Any]],
    open_questions: list[str],
) -> dict[str, Any]:
    research = detail["research"]
    return {
        "campaign": detail["campaign"],
        "summary": research["summary"],
        "messaging": research["messaging"],
        "creative": research["creative"],
        "watchouts": research["watchouts"],
        "findings": findings,
        "creative_review": creative_review,
        "assignment_review": assignment_review,
        "suggested_edits": suggested_edits,
        "open_questions": open_questions,
        "ads": [_ad_context(ad) for ad in detail["ads"][:30]],
    }


def _ad_context(ad: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "ad_id",
        "brand_name",
        "advertiser_name",
        "primary_category",
        "subcategory",
        "confidence",
        "similarity_score",
        "assigned_by",
        "products",
        "offers",
        "ctas",
        "prices",
        "risk_labels",
        "disclaimer_count",
        "small_print_count",
        "ocr_quality",
        "classification_evidence",
        "text_evidence",
    ]
    return {key: ad.get(key) for key in keys}


def _local_question_answer(
    question: str,
    detail: dict[str, Any],
    findings: list[dict[str, Any]],
    assignment_review: dict[str, Any],
    suggested_edits: list[dict[str, Any]],
) -> dict[str, Any]:
    research = detail["research"]
    messaging = research["messaging"]
    creative = research["creative"]
    watchouts = research["watchouts"]
    normalized = question.lower()
    evidence: list[str] = []
    if any(term in normalized for term in ("outlier", "belong", "cluster", "assignment")):
        outliers = assignment_review["outliers"]
        evidence = [item["ad_id"] for item in outliers if item.get("ad_id")]
        if outliers:
            answer = f"{len(outliers)} assigned ads need membership review."
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
    elif any(term in normalized for term in ("important", "main", "key", "priority", "priorities", "takeaway", "takeaways", "matter")):
        answer = _important_findings_answer(detail, findings)
        evidence = _finding_ad_ids(findings)
    elif any(term in normalized for term in ("product", "products", "sku", "variant")) or (
        "related" in normalized and any(term in normalized for term in ("campaign", "ad", "ads"))
    ):
        answer = _product_relationship_answer(detail)
        evidence = [
            ad["ad_id"]
            for ad in detail["ads"]
            if ad.get("ad_id") and ad.get("products")
        ]
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
        answer = (
            "That question is outside this campaign research scope. Ask about this "
            "campaign's products, offers, CTAs, creative, outliers, or evidence quality."
        )

    return {
        "question": question,
        "answer": answer,
        "evidence_ad_ids": evidence,
        "limits": "Local fallback answer; no LLM, web, landing page, or competitor evidence was used.",
        "source": "local",
    }


def _important_findings_answer(detail: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    research = detail["research"]
    parts: list[str] = []
    for finding in findings[:3]:
        parts.append(str(finding["detail"]))
    if not parts:
        offer = first_count(research["messaging"]["top_offers"])
        cta = first_count(research["messaging"]["top_ctas"])
        product = first_count(research["messaging"]["top_products"])
        if product:
            parts.append(f"Leading product signal: {product['value']}.")
        if offer:
            parts.append(f"Leading offer: {offer['value']} in {offer['count']} ads.")
        if cta:
            parts.append(f"Leading CTA: {cta['value']} in {cta['count']} ads.")
    if not parts:
        return "There is not enough local campaign evidence to rank the most important points."
    return "Most important local campaign points: " + " ".join(parts)


def _product_relationship_answer(detail: dict[str, Any]) -> str:
    research = detail["research"]
    products = research["messaging"]["top_products"]
    brands = research["summary"]["brands"]
    categories = research["summary"]["categories"]
    offers = research["messaging"]["top_offers"]
    if not products:
        return "No extracted product evidence is available for this campaign."

    product_names = [str(item["value"]) for item in products[:8]]
    brand = first_count(brands)
    category = first_count(categories)
    offer = first_count(offers)
    if len(product_names) == 1:
        return (
            f"The campaign centers on one extracted product: {product_names[0]}. "
            "There is not enough product variety to compare relationships."
        )

    context = []
    if brand:
        context.append(f"shared brand signal {brand['value']}")
    if category:
        context.append(f"shared category {category['value']}")
    if offer:
        context.append(f"repeated offer {offer['value']}")
    context_text = ", ".join(context) if context else "shared campaign assignment"
    return (
        f"The extracted products appear related through {context_text}. "
        f"Product values include: {', '.join(product_names)}. "
        "Review the assigned ads if you need to separate true SKUs from OCR/entity noise."
    )


def _mentioned_ad_ids(answer: str, detail: dict[str, Any]) -> list[str]:
    known = {str(ad["ad_id"]) for ad in detail["ads"] if ad.get("ad_id")}
    return [ad_id for ad_id in known if re.search(rf"\b{re.escape(ad_id)}\b", answer)]


def _finding_ad_ids(findings: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for finding in findings:
        for ad_id in finding.get("evidence_ad_ids", []):
            if ad_id and ad_id not in seen:
                seen.add(ad_id)
                ids.append(ad_id)
    return ids
