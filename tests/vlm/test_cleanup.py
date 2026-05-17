from __future__ import annotations

import json

from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.vlm.cleanup import _parse_cleaned


def test_parse_cleaned_returns_corrected_items():
    original = [
        OCRItem(frame_index=0, time_ms=0, text="GRANDCHEROKEE", confidence=0.7, engine="paddleocr"),
        OCRItem(frame_index=1, time_ms=500, text="0%APR financirg", confidence=0.8, engine="paddleocr"),
    ]
    raw = json.dumps({
        "cleaned_frames": [
            {"frame_index": 0, "time_ms": 0, "text": "Grand Cherokee", "confidence": 0.95},
            {"frame_index": 1, "time_ms": 500, "text": "0% APR financing", "confidence": 0.95},
        ]
    })
    result = _parse_cleaned(raw, original)
    assert len(result) == 2
    assert result[0].text == "Grand Cherokee"
    assert result[0].engine == "ocr_cleanup"
    assert result[1].text == "0% APR financing"


def test_parse_cleaned_falls_back_to_original_on_bad_json():
    original = [
        OCRItem(frame_index=0, time_ms=0, text="raw", confidence=0.7, engine="paddleocr"),
    ]
    result = _parse_cleaned("not json at all", original)
    assert result == original
    assert result[0].text == "raw"


def test_parse_cleaned_keeps_unmatched_original_frames():
    original = [
        OCRItem(frame_index=0, time_ms=0, text="frame 0", confidence=0.9, engine="paddleocr"),
        OCRItem(frame_index=5, time_ms=2500, text="frame 5", confidence=0.9, engine="paddleocr"),
    ]
    raw = json.dumps({
        "cleaned_frames": [
            {"frame_index": 0, "time_ms": 0, "text": "Frame 0 corrected", "confidence": 0.95},
        ]
    })
    result = _parse_cleaned(raw, original)
    assert len(result) == 2
    assert result[0].text == "Frame 0 corrected"
    assert result[1].text == "frame 5"
    assert result[0].frame_index == 0
    assert result[1].frame_index == 5
