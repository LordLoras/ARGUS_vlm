from __future__ import annotations

import json
import re
from typing import Any

from ad_classifier.agent.client import AgentClient, AgentClientError
from ad_classifier.campaigns.research_helpers import first_count


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
                f"{json.dumps(_context_payload(detail, findings, creative_review, assignment_review, suggested_edits), ensure_ascii=True)}"
            ),
        },
    ]
    try:
        response = client.complete(messages, enable_thinking=thinking)
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
If the question is not about this campaign, its ads, products, offers, CTAs, creative, evidence quality, or marketing implications, say it is outside this campaign research scope and suggest a campaign-specific question.
Do not answer general knowledge, philosophy, medical, legal, or web-current questions.
Do not invent products, counts, campaign names, or ad_ids. Cite ad_ids when making record-specific claims.
Keep the answer under 160 words unless the user asks for detail."""


def _context_payload(
    detail: dict[str, Any],
    findings: list[dict[str, Any]],
    creative_review: list[dict[str, Any]],
    assignment_review: dict[str, Any],
    suggested_edits: list[dict[str, Any]],
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
