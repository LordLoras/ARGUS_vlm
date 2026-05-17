from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ad_classifier.models.common import StrictModel


class CreativePanelRequest(StrictModel):
    persona_ids: list[str] | None = Field(default=None, min_length=1, max_length=6)


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


class CreativePanelReport(StrictModel):
    ad_id: str
    generated_at: datetime
    json_path: str
    report_type: str = "simulated_creative_review"
    caveat: str
    personas: list[PersonaReaction] = Field(default_factory=list)
    moderator_summary: ModeratorSummary
    evidence_sources: list[str] = Field(default_factory=list)
