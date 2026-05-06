from __future__ import annotations

import pytest

from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.paddlevl import (
    MockPaddleVLParser,
    PaddleVLGatingConfig,
    should_run_paddlevl,
)
from ad_classifier.pipeline.paddlevl.models import PaddleVLOutput
from ad_classifier.pipeline.preprocess.models import FrameAnalysis
from pathlib import Path


def _item(text: str, confidence: float | None = 0.9) -> OCRItem:
    return OCRItem(frame_index=0, time_ms=0, text=text, confidence=confidence, engine="mock")


def _frame_analysis(**kwargs) -> FrameAnalysis:
    defaults = dict(
        frame_index=0,
        time_ms=0,
        path=Path("/tmp/f.png"),
        phash="abcd1234abcd1234",
        blur_score=500.0,
        blank_std=50.0,
    )
    defaults.update(kwargs)
    return FrameAnalysis(**defaults)


# ---------------------------------------------------------------------------
# Gating logic
# ---------------------------------------------------------------------------


def test_force_all_always_triggers():
    config = PaddleVLGatingConfig(force_all=True)
    run, reason = should_run_paddlevl([_item("hello")], config)
    assert run is True
    assert reason == "force_all"


def test_no_items_never_triggers():
    config = PaddleVLGatingConfig()
    run, reason = should_run_paddlevl([], config)
    assert run is False
    assert reason == "no_ocr_items"


def test_low_mean_confidence_triggers():
    items = [_item("text", confidence=0.4), _item("more", confidence=0.5)]
    config = PaddleVLGatingConfig(mean_confidence_threshold=0.70)
    run, reason = should_run_paddlevl(items, config)
    assert run is True
    assert "low_mean_confidence" in reason


def test_any_low_item_confidence_triggers():
    # Three items: mean = (0.95 + 0.95 + 0.3) / 3 ≈ 0.73 > 0.70 → mean check passes.
    # One item at 0.3 < 0.50 → low_item_confidence fires.
    items = [
        _item("good text", confidence=0.95),
        _item("more good", confidence=0.95),
        _item("blurry", confidence=0.3),
    ]
    config = PaddleVLGatingConfig(mean_confidence_threshold=0.70, min_item_confidence_threshold=0.50)
    run, reason = should_run_paddlevl(items, config)
    assert run is True
    assert reason == "low_item_confidence"


def test_dense_text_triggers():
    long_text = "A" * 600
    items = [_item(long_text, confidence=0.9)]
    config = PaddleVLGatingConfig(dense_text_char_threshold=500)
    run, reason = should_run_paddlevl(items, config)
    assert run is True
    assert "dense_text" in reason


def test_many_short_fragments_triggers():
    items = [_item("ok", confidence=0.9) for _ in range(25)]
    config = PaddleVLGatingConfig(short_fragment_count_threshold=20, short_fragment_max_len=3)
    run, reason = should_run_paddlevl(items, config)
    assert run is True
    assert "many_short_fragments" in reason


def test_sensitive_category_triggers():
    items = [_item("normal text", confidence=0.95)]
    config = PaddleVLGatingConfig()
    run, reason = should_run_paddlevl(items, config, sensitive_category_triggered=True)
    assert run is True
    assert reason == "sensitive_category"


def test_blurry_frame_triggers():
    items = [_item("text", confidence=0.9)]
    fa = _frame_analysis(is_blurry=True)
    config = PaddleVLGatingConfig()
    run, reason = should_run_paddlevl(items, config, frame_analysis=fa)
    assert run is True
    assert reason == "low_quality_frame"


def test_high_quality_frame_does_not_trigger():
    items = [_item("clear text", confidence=0.95), _item("more text", confidence=0.92)]
    fa = _frame_analysis(is_blurry=False, is_blank=False)
    config = PaddleVLGatingConfig()
    run, reason = should_run_paddlevl(items, config, frame_analysis=fa)
    assert run is False
    assert reason == "not_needed"


# ---------------------------------------------------------------------------
# MockPaddleVLParser
# ---------------------------------------------------------------------------


def test_mock_parser_returns_fixed_output(tmp_path):
    from ad_classifier.pipeline.ocr.models import FrameRef

    img = tmp_path / "f.png"
    from PIL import Image
    Image.new("RGB", (32, 32)).save(img)

    payload = {"text": "SALE", "confidence": 0.9}
    parser = MockPaddleVLParser(parsed=payload, parse_ok=True)
    out = parser.parse(FrameRef(frame_index=3, time_ms=1500, path=img))

    assert isinstance(out, PaddleVLOutput)
    assert out.frame_index == 3
    assert out.time_ms == 1500
    assert out.parse_ok is True
    assert out.parsed == payload
    assert out.engine == "mock_paddlevl"


def test_mock_parser_can_simulate_parse_failure(tmp_path):
    from ad_classifier.pipeline.ocr.models import FrameRef

    img = tmp_path / "f.png"
    from PIL import Image
    Image.new("RGB", (32, 32)).save(img)

    parser = MockPaddleVLParser(parse_ok=False)
    out = parser.parse(FrameRef(frame_index=0, time_ms=0, path=img))

    assert out.parse_ok is False
    assert out.parsed is None
