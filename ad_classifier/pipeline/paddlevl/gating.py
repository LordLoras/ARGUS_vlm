from __future__ import annotations

from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.paddlevl.models import PaddleVLGatingConfig
from ad_classifier.pipeline.preprocess.models import FrameAnalysis


def should_run_paddlevl(
    ocr_items: list[OCRItem],
    config: PaddleVLGatingConfig,
    frame_analysis: FrameAnalysis | None = None,
    sensitive_category_triggered: bool = False,
) -> tuple[bool, str]:
    """
    Return ``(should_run, reason)`` based on OCR quality signals and config.

    All checks are OR-logic: a single condition being true is enough to trigger.
    """
    if config.force_all:
        return True, "force_all"

    if not ocr_items:
        return False, "no_ocr_items"

    confidences = [item.confidence for item in ocr_items if item.confidence is not None]

    if confidences:
        mean_conf = sum(confidences) / len(confidences)
        if mean_conf < config.mean_confidence_threshold:
            return True, f"low_mean_confidence:{mean_conf:.2f}"

        if any(c < config.min_item_confidence_threshold for c in confidences):
            return True, "low_item_confidence"

    total_chars = sum(len(item.text) for item in ocr_items)
    if total_chars > config.dense_text_char_threshold:
        return True, f"dense_text:{total_chars}"

    short_frags = sum(
        1 for item in ocr_items if len(item.text.strip()) <= config.short_fragment_max_len
    )
    if short_frags >= config.short_fragment_count_threshold:
        return True, f"many_short_fragments:{short_frags}"

    if sensitive_category_triggered:
        return True, "sensitive_category"

    if frame_analysis is not None and (frame_analysis.is_blurry or frame_analysis.is_blank):
        return True, "low_quality_frame"

    return False, "not_needed"
