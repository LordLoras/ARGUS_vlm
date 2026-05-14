from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

from ad_classifier.config import VLMComplexityConfig
from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.pipeline.ocr.models import OCRItem

ComplexityLevel = Literal["normal", "complex"]


@dataclass(frozen=True)
class VLMComplexity:
    level: ComplexityLevel
    score: int
    reasons: tuple[str, ...]
    metrics: dict[str, int]

    @property
    def is_complex(self) -> bool:
        return self.level == "complex"


def assess_vlm_complexity(
    *,
    ocr_items: list[OCRItem],
    transcript: WhisperTranscript,
    kept_frames: list[Any] | None = None,
    config: VLMComplexityConfig | None = None,
) -> VLMComplexity:
    cfg = config or VLMComplexityConfig()
    metrics = _complexity_metrics(ocr_items, transcript, kept_frames or [])
    if not cfg.enabled:
        return VLMComplexity(level="normal", score=0, reasons=(), metrics=metrics)

    reasons: list[str] = []
    if metrics["ocr_items"] >= cfg.ocr_item_threshold:
        reasons.append("many_ocr_items")
    if metrics["ocr_chars"] >= cfg.ocr_char_threshold:
        reasons.append("high_ocr_chars")
    if metrics["max_frame_ocr_chars"] >= cfg.max_frame_ocr_chars_threshold:
        reasons.append("dense_text_frame")
    if metrics["transcript_chars"] >= cfg.transcript_char_threshold:
        reasons.append("long_transcript")
    if metrics["kept_frames"] >= cfg.kept_frame_threshold:
        reasons.append("many_kept_frames")

    score = len(reasons)
    if metrics["ocr_chars"] >= cfg.ocr_char_threshold * 2:
        score += 1
    if metrics["ocr_items"] >= cfg.ocr_item_threshold * 2:
        score += 1

    level: ComplexityLevel = "complex" if score >= 2 else "normal"
    return VLMComplexity(
        level=level,
        score=score,
        reasons=tuple(reasons),
        metrics=metrics,
    )


def token_budget_for(
    complexity: VLMComplexity,
    *,
    normal_tokens: int,
    complex_tokens: int,
) -> int:
    if complexity.is_complex:
        return max(normal_tokens, complex_tokens)
    return normal_tokens


def _complexity_metrics(
    ocr_items: list[OCRItem],
    transcript: WhisperTranscript,
    kept_frames: list[Any],
) -> dict[str, int]:
    chars_by_frame: dict[int, int] = defaultdict(int)
    for item in ocr_items:
        chars_by_frame[item.frame_index] += len(item.text or "")

    transcript_text = transcript.text or " ".join(seg.text for seg in transcript.segments)
    return {
        "ocr_items": len(ocr_items),
        "ocr_chars": sum(len(item.text or "") for item in ocr_items),
        "ocr_frames": len(chars_by_frame),
        "max_frame_ocr_chars": max(chars_by_frame.values(), default=0),
        "transcript_chars": len(transcript_text),
        "kept_frames": len(kept_frames),
    }
