from __future__ import annotations

import json
import re
from typing import Any


def parse_research_report(
    raw: str,
    *,
    finish_reason: str | None,
    question: str | None,
    detail: dict[str, Any],
) -> dict[str, Any] | None:
    parsed = _extract_json_object(raw)
    if not parsed:
        return None
    known_ad_ids = [str(ad["ad_id"]) for ad in detail["ads"] if ad.get("ad_id")]
    return {
        "source": "llm",
        "finish_reason": finish_reason,
        "findings": _coerce_findings(parsed.get("findings"), known_ad_ids),
        "creative_review": _coerce_creative_review(parsed.get("creative_review")),
        "suggested_edits": _coerce_suggested_edits(parsed.get("suggested_edits")),
        "open_questions": _coerce_strings(parsed.get("open_questions"), limit=5),
        "question_answer": _coerce_question_answer(
            parsed.get("question_answer"),
            question,
            known_ad_ids,
        ),
    }


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _coerce_findings(value: Any, known_ad_ids: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    findings: list[dict[str, Any]] = []
    for item in value[:6]:
        if not isinstance(item, dict):
            continue
        title = _string(item.get("title"))
        detail = _string(item.get("detail"))
        if not title or not detail:
            continue
        priority = _string(item.get("priority")) or "medium"
        findings.append(
            {
                "priority": priority if priority in {"high", "medium", "low"} else "medium",
                "title": title,
                "detail": detail,
                "evidence_ad_ids": _coerce_ad_ids(item.get("evidence_ad_ids"), known_ad_ids),
            }
        )
    return findings


def _coerce_creative_review(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    review: list[dict[str, Any]] = []
    for item in value[:4]:
        if not isinstance(item, dict):
            continue
        area = _string(item.get("area"))
        detail = _string(item.get("detail"))
        if not area or not detail:
            continue
        review.append(
            {
                "area": area,
                "status": _string(item.get("status")) or "review",
                "detail": detail,
            }
        )
    return review


def _coerce_suggested_edits(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    suggestions: list[dict[str, Any]] = []
    for item in value[:4]:
        if not isinstance(item, dict):
            continue
        field = _string(item.get("field"))
        candidate = _string(item.get("value"))
        reason = _string(item.get("reason"))
        if field and candidate and reason:
            suggestions.append({"field": field, "value": candidate, "reason": reason})
    return suggestions


def _coerce_question_answer(
    value: Any,
    question: str | None,
    known_ad_ids: list[str],
) -> dict[str, Any] | None:
    if not question:
        return None
    if not isinstance(value, dict):
        return None
    answer = _string(value.get("answer"))
    if not answer:
        return None
    return {
        "question": _string(value.get("question")) or question,
        "answer": answer,
        "evidence_ad_ids": _coerce_ad_ids(value.get("evidence_ad_ids"), known_ad_ids)
        or _mentioned_ad_ids(answer, known_ad_ids),
        "limits": _string(value.get("limits"))
        or "LLM answer grounded only in local campaign evidence.",
        "source": "llm",
    }


def _coerce_strings(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _string(item)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _coerce_ad_ids(value: Any, known_ad_ids: list[str]) -> list[str]:
    ad_ids = _coerce_strings(value, limit=12)
    known = set(known_ad_ids)
    return [ad_id for ad_id in ad_ids if ad_id in known]


def _mentioned_ad_ids(answer: str, known_ad_ids: list[str]) -> list[str]:
    return [ad_id for ad_id in known_ad_ids if re.search(rf"\b{re.escape(ad_id)}\b", answer)]


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
