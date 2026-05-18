from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from ad_classifier.pipeline.ocr import FrameRef, MockOCREngine, OCRItem, PaddleOCREngine


def _frame(path: Path, idx: int = 0, t: int = 0) -> FrameRef:
    return FrameRef(frame_index=idx, time_ms=t, path=path)


# ---------------------------------------------------------------------------
# MockOCREngine
# ---------------------------------------------------------------------------


def test_mock_engine_returns_empty_by_default(tmp_path):
    img = tmp_path / "f.png"
    Image.new("RGB", (32, 32)).save(img)
    engine = MockOCREngine()
    assert engine.extract(_frame(img)) == []


def test_mock_engine_retags_frame_coords(tmp_path):
    img = tmp_path / "f.png"
    Image.new("RGB", (32, 32)).save(img)
    seed = [OCRItem(frame_index=0, time_ms=0, text="SALE 50% OFF", confidence=0.95, engine="mock")]
    engine = MockOCREngine(items=seed)

    result = engine.extract(FrameRef(frame_index=7, time_ms=3500, path=img))

    assert len(result) == 1
    assert result[0].frame_index == 7
    assert result[0].time_ms == 3500
    assert result[0].text == "SALE 50% OFF"
    assert result[0].engine == "mock"


def test_mock_engine_preserves_raw_text(tmp_path):
    img = tmp_path / "f.png"
    Image.new("RGB", (32, 32)).save(img)
    # Text with policy-like content must not be normalised away
    raw = "No credit check! APR as low as 9.9%."
    seed = [OCRItem(frame_index=0, time_ms=0, text=raw, confidence=0.8, engine="mock")]
    engine = MockOCREngine(items=seed)

    result = engine.extract(_frame(img))

    assert result[0].text == raw


def test_mock_engine_handles_multiple_items(tmp_path):
    img = tmp_path / "f.png"
    Image.new("RGB", (32, 32)).save(img)
    items = [
        OCRItem(frame_index=0, time_ms=0, text="Line 1", confidence=0.9, engine="mock"),
        OCRItem(frame_index=0, time_ms=0, text="Line 2", confidence=0.7, engine="mock"),
    ]
    engine = MockOCREngine(items=items)
    result = engine.extract(_frame(img))
    assert len(result) == 2
    assert [r.text for r in result] == ["Line 1", "Line 2"]


# ---------------------------------------------------------------------------
# PaddleOCREngine — import guard only (no real paddle in tests)
# ---------------------------------------------------------------------------


def test_paddleocr_engine_raises_clear_import_error(tmp_path, monkeypatch):
    img = tmp_path / "f.png"
    Image.new("RGB", (32, 32)).save(img)

    # Simulate PaddleOCR not installed
    import builtins

    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in ("paddle", "paddleocr"):
            raise ImportError("No module named 'paddle'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    engine = PaddleOCREngine(device="cpu")
    with pytest.raises(ImportError, match="PaddleOCR is not installed"):
        engine.extract(_frame(img))


# ---------------------------------------------------------------------------
# FrameRef / OCRItem model validation
# ---------------------------------------------------------------------------


def test_frameref_rejects_negative_index():
    with pytest.raises(ValidationError):
        FrameRef(frame_index=-1, time_ms=0, path=Path("/tmp/f.png"))


def test_ocr_item_rejects_confidence_out_of_range():
    with pytest.raises(ValidationError):
        OCRItem(frame_index=0, time_ms=0, text="hi", confidence=1.5, engine="test")
