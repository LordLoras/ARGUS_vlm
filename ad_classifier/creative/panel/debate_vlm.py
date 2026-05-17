from __future__ import annotations

import json
from typing import Any

from ad_classifier.agent.client import AgentClient
from ad_classifier.creative.panel.models import (
    DebateScorecard,
    DebateTension,
    DebateTurn,
    ModeratorSummary,
    PersonaReaction,
)
from ad_classifier.creative.panel.service import (
    _PanelContext,
    _citations_from_ids,
    _compact_evidence,
    _complete_json,
    _required_str,
    _str_list,
    _summary_from_vlm,
)


def run_vlm_debate(
    client: AgentClient,
    context: _PanelContext,
    topic: str,
    participants: list[PersonaReaction],
    *,
    fallback_opening: list[DebateTurn],
    fallback_cross: list[DebateTurn],
    fallback_closing: list[DebateTurn],
    fallback_tensions: list[DebateTension],
    fallback_scorecard: DebateScorecard,
    fallback_summary: ModeratorSummary,
    thinking: bool,
) -> tuple[
    list[DebateTurn],
    list[DebateTurn],
    list[DebateTurn],
    list[DebateTension],
    DebateScorecard,
    ModeratorSummary,
    bool,
]:
    raw = _complete_json(
        client,
        _debate_messages(context, topic, participants),
        thinking=thinking,
        label="creative_debate",
    )
    used_fallback = False

    opening = _turns_from_vlm(
        raw.get("opening_statements"),
        "opening",
        context,
        participants,
    )
    if not opening:
        opening = fallback_opening
        used_fallback = True

    cross = _turns_from_vlm(
        raw.get("cross_examination"),
        "challenge",
        context,
        participants,
    )
    if not cross:
        cross = fallback_cross
        used_fallback = True

    closing = _turns_from_vlm(
        raw.get("closing_statements"),
        "closing",
        context,
        participants,
    )
    if not closing:
        closing = fallback_closing
        used_fallback = True

    tensions = _tensions_from_vlm(raw.get("tensions"))
    if not tensions:
        tensions = fallback_tensions
        used_fallback = True

    scorecard = _scorecard_from_vlm(raw.get("scorecard"))
    if scorecard is None:
        scorecard = fallback_scorecard
        used_fallback = True

    try:
        summary = _summary_from_vlm(raw.get("moderator_summary"))
    except ValueError:
        summary = fallback_summary
        used_fallback = True
    else:
        if not any(
            [
                summary.consensus,
                summary.disagreements,
                summary.message_clarity_issues,
                summary.strongest_hooks,
                summary.suggested_ab_variants,
            ]
        ):
            summary = fallback_summary
            used_fallback = True

    return opening, cross, closing, tensions, scorecard, summary, used_fallback


def _debate_messages(
    context: _PanelContext,
    topic: str,
    participants: list[PersonaReaction],
) -> list[dict[str, str]]:
    participant_payload = [
        {
            "persona_id": item.persona_id,
            "label": item.persona_label,
            "lens": item.lens,
            "first_impression": item.first_impression,
            "understood_product_or_offer": item.understood_product_or_offer,
            "likely_objection": item.likely_objection,
            "trust_points": item.trust_points[:2],
            "confusion_points": item.confusion_points[:2],
        }
        for item in participants
    ]
    payload = {
        "ad_id": context.ad_id,
        "topic": topic,
        "evidence": _compact_evidence(context),
        "participants": participant_payload,
    }
    system = (
        "You are ARGUS Creative Debate Panel, a local-first ad analysis assistant. "
        "Run a compact adversarial debate between the supplied persona lenses about the topic. "
        "Internally reason from ad evidence and persona objections before answering, but do not "
        "reveal chain-of-thought. Make personas challenge each other's claims using only supplied "
        "evidence and citation ids. If support is missing, mark it as unclear. Do not stereotype, "
        "invent offers/prices/CTAs, make policy claims, or forecast market response, sales lift, "
        "or percentages. Observation tags are descriptive, not violations. Keep it sharp and "
        "evidence-backed. Return one compact JSON object only."
    )
    user = (
        f"Debate payload:\n{json.dumps(payload, ensure_ascii=True, separators=(',', ':'))}\n\n"
        "Return strict JSON with this exact shape:\n"
        f"{json.dumps(_debate_schema(), ensure_ascii=True, separators=(',', ':'))}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _debate_schema() -> dict[str, Any]:
    turn = {
        "speaker_persona_id": "persona id",
        "stance": "advocate|skeptic|explorer",
        "claim": "max 22 words",
        "evidence_read": "max 20 words",
        "pressure_test": "max 18 words",
        "citation_ids": ["c0"],
    }
    challenge = {**turn, "target_persona_id": "persona id or null"}
    return {
        "opening_statements": [turn],
        "cross_examination": [challenge],
        "closing_statements": [turn],
        "tensions": [
            {
                "axis": "max 6 words",
                "advocate": "max 14 words",
                "skeptic": "max 14 words",
                "moderator_take": "max 18 words",
            }
        ],
        "scorecard": {
            "moderator_verdict": "max 24 words",
            "strongest_argument": "max 18 words",
            "weakest_argument": "max 18 words",
            "unresolved_questions": ["max 3 items"],
            "recommended_tests": ["max 3 items"],
        },
        "moderator_summary": {
            "consensus": ["max 3 items"],
            "disagreements": ["max 2 items"],
            "message_clarity_issues": ["max 3 items"],
            "strongest_hooks": ["max 3 items"],
            "suggested_ab_variants": ["max 3 items"],
        },
    }


def _turns_from_vlm(
    raw: Any,
    phase: str,
    context: _PanelContext,
    participants: list[PersonaReaction],
) -> list[DebateTurn]:
    if not isinstance(raw, list):
        return []
    by_id = {reaction.persona_id: reaction for reaction in participants}
    turns: list[DebateTurn] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        speaker_id = str(item.get("speaker_persona_id") or "")
        speaker = by_id.get(speaker_id)
        if speaker is None:
            continue
        target_id = item.get("target_persona_id")
        target = str(target_id) if target_id in by_id else None
        try:
            turns.append(
                DebateTurn(
                    round_index=int(item.get("round_index") or idx + 1),
                    phase=phase,  # type: ignore[arg-type]
                    speaker_persona_id=speaker.persona_id,
                    speaker_label=speaker.persona_label,
                    stance=_safe_stance(item.get("stance"), speaker.persona_id),
                    target_persona_id=target,
                    claim=_required_str(item, "claim"),
                    evidence_read=_required_str(item, "evidence_read"),
                    pressure_test=_required_str(item, "pressure_test"),
                    citations=_citations_from_ids(item.get("citation_ids"), context)
                    or (speaker.citations or context.citations)[:3],
                )
            )
        except (TypeError, ValueError):
            continue
    return turns[:12]


def _tensions_from_vlm(raw: Any) -> list[DebateTension]:
    if not isinstance(raw, list):
        return []
    tensions: list[DebateTension] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            tensions.append(
                DebateTension(
                    axis=_required_str(item, "axis"),
                    advocate=_required_str(item, "advocate"),
                    skeptic=_required_str(item, "skeptic"),
                    moderator_take=_required_str(item, "moderator_take"),
                )
            )
        except ValueError:
            continue
    return tensions[:6]


def _scorecard_from_vlm(raw: Any) -> DebateScorecard | None:
    if not isinstance(raw, dict):
        return None
    try:
        return DebateScorecard(
            moderator_verdict=_required_str(raw, "moderator_verdict"),
            strongest_argument=_required_str(raw, "strongest_argument"),
            weakest_argument=_required_str(raw, "weakest_argument"),
            unresolved_questions=_str_list(raw.get("unresolved_questions"))[:5],
            recommended_tests=_str_list(raw.get("recommended_tests"))[:5],
        )
    except ValueError:
        return None


def _safe_stance(raw: Any, persona_id: str) -> str:
    value = str(raw or "").strip().lower()
    if value in {"advocate", "skeptic", "moderator", "explorer"}:
        return value
    if persona_id in {"skeptical_buyer", "compliance_reviewer"}:
        return "skeptic"
    if persona_id == "first_time_car_buyer":
        return "explorer"
    return "advocate"
