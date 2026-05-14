from __future__ import annotations

from pathlib import Path

from ad_classifier.config import VLMComplexityConfig
from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.preprocess.models import FrameAnalysis
from ad_classifier.vlm.complexity import assess_vlm_complexity, token_budget_for


def _ocr_item(frame_index: int, text: str) -> OCRItem:
    return OCRItem(
        frame_index=frame_index,
        time_ms=frame_index * 500,
        text=text,
        confidence=0.9,
        engine="paddleocr",
    )


def test_assess_vlm_complexity_marks_dense_text_ad_complex():
    ocr_items = [_ocr_item(idx % 30, "SALE TEXT " * 2) for idx in range(130)]
    ocr_items.append(_ocr_item(40, "X" * 220))
    frames = [
        FrameAnalysis(frame_index=idx, time_ms=idx * 500, path=Path(f"{idx}.png"))
        for idx in range(28)
    ]

    result = assess_vlm_complexity(
        ocr_items=ocr_items,
        transcript=WhisperTranscript(text="short transcript"),
        kept_frames=frames,
        config=VLMComplexityConfig(),
    )

    assert result.is_complex is True
    assert result.level == "complex"
    assert "many_ocr_items" in result.reasons
    assert "dense_text_frame" in result.reasons
    assert result.metrics["kept_frames"] == 28


def test_assess_vlm_complexity_keeps_simple_ad_normal():
    result = assess_vlm_complexity(
        ocr_items=[_ocr_item(0, "Jeep")],
        transcript=WhisperTranscript(text="short"),
        kept_frames=[FrameAnalysis(frame_index=0, time_ms=0, path=Path("0.png"))],
        config=VLMComplexityConfig(),
    )

    assert result.is_complex is False
    assert result.reasons == ()


def test_token_budget_for_complexity_raises_only_complex_ads():
    normal = assess_vlm_complexity(
        ocr_items=[_ocr_item(0, "short")],
        transcript=WhisperTranscript(text="short"),
        kept_frames=[],
        config=VLMComplexityConfig(),
    )
    complex_result = assess_vlm_complexity(
        ocr_items=[_ocr_item(idx, "A" * 20) for idx in range(130)],
        transcript=WhisperTranscript(text="short"),
        kept_frames=[],
        config=VLMComplexityConfig(),
    )

    assert token_budget_for(normal, normal_tokens=4096, complex_tokens=8192) == 4096
    assert token_budget_for(complex_result, normal_tokens=4096, complex_tokens=8192) == 8192
