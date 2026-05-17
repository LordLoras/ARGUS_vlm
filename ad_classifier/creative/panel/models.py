from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ad_classifier.models.common import StrictModel


class CreativePanelRequest(StrictModel):
    persona_ids: list[str] | None = Field(default=None, min_length=1, max_length=6)
    use_vlm: bool = True
    enable_reasoning: bool = True


class CreativeDebateRequest(CreativePanelRequest):
    topic: str | None = Field(default=None, max_length=160)


class PanelCitation(StrictModel):
    ad_id: str
    time_ms: int | None = Field(default=None, ge=0)
    frame_index: int | None = Field(default=None, ge=0)
    source: str
    text: str


class PersonaReaction(StrictModel):
    persona_id: str
    persona_label: str
    lens: str
    first_impression: str
    understood_product_or_offer: str
    emotional_reaction: str
    trust_points: list[str] = Field(default_factory=list)
    confusion_points: list[str] = Field(default_factory=list)
    likely_objection: str
    memorable_moment: str
    cta_likelihood: str
    citations: list[PanelCitation] = Field(default_factory=list)


class ModeratorSummary(StrictModel):
    consensus: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    message_clarity_issues: list[str] = Field(default_factory=list)
    strongest_hooks: list[str] = Field(default_factory=list)
    suggested_ab_variants: list[str] = Field(default_factory=list)


class DebateTurn(StrictModel):
    round_index: int = Field(ge=1)
    phase: Literal["opening", "challenge", "rebuttal", "closing"]
    speaker_persona_id: str
    speaker_label: str
    stance: Literal["advocate", "skeptic", "moderator", "explorer"]
    target_persona_id: str | None = None
    claim: str
    evidence_read: str
    pressure_test: str
    citations: list[PanelCitation] = Field(default_factory=list)


class DebateTension(StrictModel):
    axis: str
    advocate: str
    skeptic: str
    moderator_take: str


class DebateScorecard(StrictModel):
    moderator_verdict: str
    strongest_argument: str
    weakest_argument: str
    unresolved_questions: list[str] = Field(default_factory=list)
    recommended_tests: list[str] = Field(default_factory=list)


class CreativePanelReport(StrictModel):
    ad_id: str
    generated_at: datetime
    json_path: str
    report_type: str = "simulated_creative_review"
    analysis_source: Literal["vlm", "vlm_with_fallback", "deterministic_fallback"] = (
        "deterministic_fallback"
    )
    source_model: str | None = None
    fallback_error: str | None = None
    caveat: str
    personas: list[PersonaReaction] = Field(default_factory=list)
    moderator_summary: ModeratorSummary
    evidence_sources: list[str] = Field(default_factory=list)


class CreativeDebateReport(StrictModel):
    ad_id: str
    generated_at: datetime
    json_path: str
    report_type: str = "simulated_creative_debate"
    analysis_source: Literal["vlm", "vlm_with_fallback", "deterministic_fallback"] = (
        "deterministic_fallback"
    )
    source_model: str | None = None
    fallback_error: str | None = None
    topic: str
    caveat: str
    participants: list[PersonaReaction] = Field(default_factory=list)
    opening_statements: list[DebateTurn] = Field(default_factory=list)
    cross_examination: list[DebateTurn] = Field(default_factory=list)
    closing_statements: list[DebateTurn] = Field(default_factory=list)
    tensions: list[DebateTension] = Field(default_factory=list)
    scorecard: DebateScorecard
    moderator_summary: ModeratorSummary
    evidence_sources: list[str] = Field(default_factory=list)
