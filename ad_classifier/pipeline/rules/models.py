from __future__ import annotations

from typing import Literal

from pydantic import Field

from ad_classifier.models.common import StrictModel

MatchType = Literal["keyword", "regex"]
Severity = Literal["high", "medium", "low"]
RuleSource = Literal["ocr", "transcript"]


class Rule(StrictModel):
    id: str
    pattern: str
    match_type: MatchType = "keyword"
    case_insensitive: bool = True
    # Which evidence sources to scan (ocr, transcript, or both listed)
    sources: list[RuleSource] = Field(default_factory=lambda: ["ocr", "transcript"])
    category: str | None = None
    risk_label: str | None = None
    severity: Severity = "medium"


class RuleTrigger(StrictModel):
    rule_id: str
    category: str | None = None
    risk_label: str | None = None
    severity: Severity = "medium"
    evidence_text: str
    source: RuleSource
    time_ms: int | None = Field(default=None, ge=0)
    frame_index: int | None = Field(default=None, ge=0)
