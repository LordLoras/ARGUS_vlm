from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import structlog

from ad_classifier.agent.client import AgentClient
from ad_classifier.creative.panel.debate_vlm import run_vlm_debate
from ad_classifier.creative.panel.models import (
    CreativeDebateReport,
    DebateScorecard,
    DebateTension,
    DebateTurn,
    ModeratorSummary,
    PersonaReaction,
)
from ad_classifier.creative.panel.service import (
    DEFAULT_PERSONAS,
    PERSONAS,
    _build_context,
    _evidence_sources,
    _moderator_summary,
    _offer_phrase,
    _PanelContext,
    _product_phrase,
    _reaction,
)

logger = structlog.get_logger(__name__)


def build_creative_debate(
    conn: sqlite3.Connection,
    ad_id: str,
    out_root: Path,
    persona_ids: list[str] | None = None,
    *,
    topic: str | None = None,
    use_vlm: bool = False,
    llm_client: AgentClient | None = None,
    source_model: str | None = None,
    thinking: bool = False,
) -> CreativeDebateReport:
    selected = persona_ids or DEFAULT_PERSONAS
    unknown = [persona_id for persona_id in selected if persona_id not in PERSONAS]
    if unknown:
        raise ValueError(f"unknown persona ids: {', '.join(unknown)}")

    context = _build_context(conn, ad_id)
    topic_text = (topic or "").strip() or _default_debate_topic(context)
    participants = [_reaction(PERSONAS[persona_id], context) for persona_id in selected]
    (
        opening_statements,
        cross_examination,
        closing_statements,
        tensions,
        scorecard,
        moderator_summary,
    ) = _deterministic_debate(context, participants)
    analysis_source = "deterministic_fallback"
    fallback_error: str | None = None

    if use_vlm and llm_client is not None:
        try:
            (
                opening_statements,
                cross_examination,
                closing_statements,
                tensions,
                scorecard,
                moderator_summary,
                used_fallback,
            ) = run_vlm_debate(
                llm_client,
                context,
                topic_text,
                participants,
                fallback_opening=opening_statements,
                fallback_cross=cross_examination,
                fallback_closing=closing_statements,
                fallback_tensions=tensions,
                fallback_scorecard=scorecard,
                fallback_summary=moderator_summary,
                thinking=thinking,
            )
            analysis_source = "vlm_with_fallback" if used_fallback else "vlm"
        except Exception as exc:
            fallback_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "creative_debate_vlm_failed",
                ad_id=ad_id,
                error=fallback_error,
            )
    elif use_vlm:
        fallback_error = "VLM client unavailable"

    report = CreativeDebateReport(
        ad_id=ad_id,
        generated_at=datetime.now(UTC),
        json_path=str(out_root / ad_id / "creative_debate.json"),
        analysis_source=analysis_source,
        source_model=source_model if analysis_source.startswith("vlm") else None,
        fallback_error=fallback_error,
        topic=topic_text,
        caveat=(
            "Simulated creative debate generated from stored ARGUS evidence. "
            "It is not a real focus group, demographic sample, or market forecast."
        ),
        participants=participants,
        opening_statements=opening_statements,
        cross_examination=cross_examination,
        closing_statements=closing_statements,
        tensions=tensions,
        scorecard=scorecard,
        moderator_summary=moderator_summary,
        evidence_sources=_evidence_sources(context),
    )

    output_dir = out_root / ad_id
    output_dir.mkdir(parents=True, exist_ok=True)
    Path(report.json_path).write_text(
        json.dumps(report.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return report


def _deterministic_debate(
    context: _PanelContext,
    participants: list[PersonaReaction],
) -> tuple[
    list[DebateTurn],
    list[DebateTurn],
    list[DebateTurn],
    list[DebateTension],
    DebateScorecard,
    ModeratorSummary,
]:
    summary = _moderator_summary(context, participants)
    opening = [
        DebateTurn(
            round_index=1,
            phase="opening",
            speaker_persona_id=reaction.persona_id,
            speaker_label=reaction.persona_label,
            stance=_stance_for_persona(reaction.persona_id),
            claim=reaction.first_impression,
            evidence_read=reaction.understood_product_or_offer,
            pressure_test=reaction.likely_objection,
            citations=(reaction.citations or context.citations)[:3],
        )
        for reaction in participants
    ]

    cross: list[DebateTurn] = []
    for idx, reaction in enumerate(participants):
        target = participants[(idx + 1) % len(participants)] if len(participants) > 1 else None
        challenge = (
            reaction.confusion_points[0] if reaction.confusion_points else reaction.likely_objection
        )
        target_phrase = (
            f"Challenges {target.persona_label}: "
            if target is not None
            else "Challenges the creative: "
        )
        cross.append(
            DebateTurn(
                round_index=idx + 1,
                phase="challenge",
                speaker_persona_id=reaction.persona_id,
                speaker_label=reaction.persona_label,
                stance=_stance_for_persona(reaction.persona_id),
                target_persona_id=target.persona_id if target is not None else None,
                claim=f"{target_phrase}{challenge}",
                evidence_read=_join_short(
                    reaction.trust_points[:1] + reaction.confusion_points[:1]
                ),
                pressure_test=reaction.likely_objection,
                citations=(reaction.citations or context.citations)[:3],
            )
        )

    closing = [
        DebateTurn(
            round_index=1,
            phase="closing",
            speaker_persona_id=reaction.persona_id,
            speaker_label=reaction.persona_label,
            stance=_stance_for_persona(reaction.persona_id),
            claim=f"Keep {reaction.memorable_moment}; resolve {reaction.likely_objection.lower()}",
            evidence_read=reaction.cta_likelihood,
            pressure_test="Can this be proven from the ad evidence?",
            citations=(reaction.citations or context.citations)[:2],
        )
        for reaction in participants
    ]

    tensions = _deterministic_tensions(context)
    unresolved = summary.message_clarity_issues[:3] or [
        "What evidence makes the next action clear?"
    ]
    tests = summary.suggested_ab_variants[:3] or ["Test a clearer product-and-CTA end card."]
    strongest = (
        summary.strongest_hooks[0]
        if summary.strongest_hooks
        else "The clearest extracted evidence."
    )
    weakest = unresolved[0]
    scorecard = DebateScorecard(
        moderator_verdict=(
            "The hook can work if the creative resolves the debate around proof, terms, and next step clarity."
        ),
        strongest_argument=strongest,
        weakest_argument=weakest,
        unresolved_questions=unresolved,
        recommended_tests=tests,
    )
    return opening, cross, closing, tensions, scorecard, summary


def _deterministic_tensions(context: _PanelContext) -> list[DebateTension]:
    tensions = [
        DebateTension(
            axis="Value vs proof",
            advocate=_offer_phrase(context),
            skeptic="The exact terms still need to be easy to verify.",
            moderator_take="Lead with the strongest extracted offer, then anchor it with terms.",
        )
    ]
    if context.ctas:
        tensions.append(
            DebateTension(
                axis="Action vs motivation",
                advocate=f"CTA cue is present: {context.ctas[0]}.",
                skeptic="The CTA only works if the reason to act is already clear.",
                moderator_take="Connect the CTA directly to the main benefit.",
            )
        )
    if context.disclaimers or context.risk_labels:
        tensions.append(
            DebateTension(
                axis="Persuasion vs qualifiers",
                advocate="Strong claims can create urgency and memorability.",
                skeptic="Qualifiers and observation tags need visible context.",
                moderator_take="Keep claims close to the evidence that supports or qualifies them.",
            )
        )
    return tensions[:4]


def _stance_for_persona(persona_id: str) -> str:
    if persona_id in {"skeptical_buyer", "compliance_reviewer"}:
        return "skeptic"
    if persona_id in {"first_time_car_buyer"}:
        return "explorer"
    return "advocate"


def _default_debate_topic(context: _PanelContext) -> str:
    product = _product_phrase(context)
    return f"What will make {product} persuasive while staying grounded in the extracted evidence?"


def _join_short(items: list[str]) -> str:
    cleaned = [item.strip() for item in items if item.strip()]
    return " ".join(cleaned) if cleaned else "No specific supporting point was extracted."
