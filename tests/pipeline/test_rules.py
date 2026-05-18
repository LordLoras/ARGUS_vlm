from __future__ import annotations

from ad_classifier.ingest.models import TranscriptSegment, WhisperTranscript
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.rules import RulesEngine, load_rules
from ad_classifier.pipeline.rules.models import Rule


def _ocr(text: str, frame_index: int = 0, time_ms: int = 0) -> OCRItem:
    return OCRItem(frame_index=frame_index, time_ms=time_ms, text=text, engine="mock")


def _transcript(*segments: tuple[int, int, str]) -> WhisperTranscript:
    segs = [TranscriptSegment(start_ms=s, end_ms=e, text=t) for s, e, t in segments]
    return WhisperTranscript(segments=segs, text=" ".join(t for _, _, t in segments))


def _simple_rules() -> list[Rule]:
    return [
        Rule(
            id="test_keyword",
            pattern="no credit check",
            match_type="keyword",
            case_insensitive=True,
            sources=["ocr", "transcript"],
            category="financial_services",
            risk_label="misleading_claim",
            severity="high",
        ),
        Rule(
            id="test_regex",
            pattern=r"lose \d+ lbs?",
            match_type="regex",
            case_insensitive=True,
            sources=["ocr", "transcript"],
            category="health_wellness",
            risk_label="health_claim",
            severity="high",
        ),
    ]


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------


def test_keyword_match_ocr(tmp_path):
    engine = RulesEngine(_simple_rules())
    items = [_ocr("Apply now — no credit check required")]
    triggers = engine.run(ocr_items=items)
    assert len(triggers) == 1
    assert triggers[0].rule_id == "test_keyword"
    assert triggers[0].source == "ocr"
    assert triggers[0].frame_index == 0


def test_keyword_match_is_case_insensitive():
    engine = RulesEngine(_simple_rules())
    items = [_ocr("NO CREDIT CHECK AVAILABLE")]
    triggers = engine.run(ocr_items=items)
    assert any(t.rule_id == "test_keyword" for t in triggers)


def test_keyword_no_match():
    engine = RulesEngine(_simple_rules())
    items = [_ocr("Great deals on cars")]
    triggers = engine.run(ocr_items=items)
    assert triggers == []


# ---------------------------------------------------------------------------
# Regex matching
# ---------------------------------------------------------------------------


def test_regex_match_ocr():
    engine = RulesEngine(_simple_rules())
    items = [_ocr("Lose 20 lbs in 30 days!")]
    triggers = engine.run(ocr_items=items)
    health = [t for t in triggers if t.rule_id == "test_regex"]
    assert len(health) == 1
    assert health[0].category == "health_wellness"


def test_regex_match_transcript():
    engine = RulesEngine(_simple_rules())
    t = _transcript((0, 2000, "You can lose 15 lbs guaranteed"))
    triggers = engine.run(ocr_items=[], transcript=t)
    health = [t for t in triggers if t.rule_id == "test_regex"]
    assert len(health) == 1
    assert health[0].source == "transcript"
    assert health[0].frame_index is None


# ---------------------------------------------------------------------------
# Source filtering
# ---------------------------------------------------------------------------


def test_ocr_only_rule_ignores_transcript():
    rules = [
        Rule(
            id="ocr_only",
            pattern="bad credit ok",
            sources=["ocr"],
            category="financial_services",
            risk_label="misleading_claim",
            severity="high",
        )
    ]
    engine = RulesEngine(rules)
    t = _transcript((0, 1000, "bad credit ok — call now"))
    triggers = engine.run(ocr_items=[], transcript=t)
    assert triggers == []


def test_transcript_only_rule_ignores_ocr():
    rules = [
        Rule(
            id="transcript_only",
            pattern="act now",
            sources=["transcript"],
            category="general",
            risk_label="urgency_pressure",
            severity="medium",
        )
    ]
    engine = RulesEngine(rules)
    triggers = engine.run(ocr_items=[_ocr("act now")])
    assert triggers == []


# ---------------------------------------------------------------------------
# Evidence and metadata on triggers
# ---------------------------------------------------------------------------


def test_trigger_preserves_evidence_text():
    engine = RulesEngine(_simple_rules())
    raw = "No Credit Check — apply today"
    items = [_ocr(raw, frame_index=5, time_ms=2500)]
    triggers = engine.run(ocr_items=items)
    assert triggers[0].evidence_text == raw
    assert triggers[0].time_ms == 2500
    assert triggers[0].frame_index == 5


def test_multiple_rules_can_match_same_text():
    rules = [
        Rule(id="r1", pattern="guaranteed", sources=["ocr"], severity="high"),
        Rule(id="r2", pattern="no risk", sources=["ocr"], severity="medium"),
    ]
    engine = RulesEngine(rules)
    items = [_ocr("Guaranteed returns — no risk")]
    triggers = engine.run(ocr_items=items)
    rule_ids = {t.rule_id for t in triggers}
    assert "r1" in rule_ids
    assert "r2" in rule_ids


# ---------------------------------------------------------------------------
# Default rules YAML
# ---------------------------------------------------------------------------


def test_load_default_rules_returns_nonempty_list():
    rules = load_rules()
    assert len(rules) > 0
    assert all(isinstance(r, Rule) for r in rules)


def test_default_rules_trigger_financial_phrase():
    rules = load_rules()
    engine = RulesEngine(rules)
    items = [_ocr("Apply now — no credit check required!")]
    triggers = engine.run(ocr_items=items)
    financial = [t for t in triggers if t.category == "financial_services"]
    assert len(financial) >= 1


def test_load_rules_from_custom_path(tmp_path):
    yaml_path = tmp_path / "my_rules.yaml"
    yaml_path.write_text(
        "rules:\n"
        "  - id: custom_rule\n"
        "    pattern: 'test pattern'\n"
        "    match_type: keyword\n"
        "    sources: [ocr]\n"
        "    severity: low\n",
        encoding="utf-8",
    )
    rules = load_rules(yaml_path)
    assert len(rules) == 1
    assert rules[0].id == "custom_rule"
