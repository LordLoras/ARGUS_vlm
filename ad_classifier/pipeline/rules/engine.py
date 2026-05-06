from __future__ import annotations

import re as _re

from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.rules.models import Rule, RuleTrigger


class RulesEngine:
    """
    Deterministic rule runner over OCR text and transcript segments.

    Supports keyword and regex matching with optional case folding.
    Each matched (rule, evidence) pair produces one RuleTrigger.
    """

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    def run(
        self,
        ocr_items: list[OCRItem],
        transcript: WhisperTranscript | None = None,
    ) -> list[RuleTrigger]:
        triggers: list[RuleTrigger] = []
        for rule in self._rules:
            if "ocr" in rule.sources:
                for item in ocr_items:
                    if self._matches(rule, item.text):
                        triggers.append(
                            RuleTrigger(
                                rule_id=rule.id,
                                category=rule.category,
                                risk_label=rule.risk_label,
                                severity=rule.severity,
                                evidence_text=item.text,
                                source="ocr",
                                time_ms=item.time_ms,
                                frame_index=item.frame_index,
                            )
                        )

            if "transcript" in rule.sources and transcript is not None:
                for seg in transcript.segments:
                    if self._matches(rule, seg.text):
                        triggers.append(
                            RuleTrigger(
                                rule_id=rule.id,
                                category=rule.category,
                                risk_label=rule.risk_label,
                                severity=rule.severity,
                                evidence_text=seg.text,
                                source="transcript",
                                time_ms=seg.start_ms,
                                frame_index=None,
                            )
                        )
        return triggers

    @staticmethod
    def _matches(rule: Rule, text: str) -> bool:
        haystack = text.lower() if rule.case_insensitive else text
        needle = rule.pattern.lower() if rule.case_insensitive else rule.pattern
        if rule.match_type == "keyword":
            return needle in haystack
        return bool(_re.search(needle, haystack))
