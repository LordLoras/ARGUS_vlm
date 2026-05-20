from __future__ import annotations

from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.pipeline.alignment import align_transcript_to_frame
from ad_classifier.pipeline.evidence.models import EvidenceBundle, FrameSummary
from ad_classifier.pipeline.ocr.fine_print import split_fine_print
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.paddlevl.models import PaddleVLOutput
from ad_classifier.pipeline.preprocess.models import FrameAnalysis
from ad_classifier.pipeline.rules.models import RuleTrigger

_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


def _select_frames(
    kept_frames: list[FrameAnalysis],
    rules_triggered: list[RuleTrigger],
    ocr_by_frame: dict[int, list[OCRItem]],
    max_frames: int,
) -> list[tuple[FrameAnalysis, str]]:
    """
    Deterministic frame selection per H.1 priority order:

    1. First and last kept frames (always).
    2. Rule-trigger frames sorted by severity (high → medium → low), then frame_index.
    3. Frames with most OCR text (descending char count).
    4. Even time distribution: greedy pick furthest from already-selected times.
    5. Tiebreak: ascending frame_index throughout.

    Returns list of (FrameAnalysis, selection_reason) sorted by frame_index.
    """
    if not kept_frames:
        return []

    if len(kept_frames) <= max_frames:
        return [(f, "all_frames") for f in kept_frames]

    # Map for fast lookup
    by_index: dict[int, FrameAnalysis] = {f.frame_index: f for f in kept_frames}

    # selected: frame_index → (frame, reason)
    selected: dict[int, tuple[FrameAnalysis, str]] = {}

    def _add(frame: FrameAnalysis, reason: str) -> None:
        if frame.frame_index not in selected:
            selected[frame.frame_index] = (frame, reason)

    # 1. First and last
    _add(kept_frames[0], "first")
    _add(kept_frames[-1], "last")
    if len(selected) >= max_frames:
        return _sorted(selected)

    # 2. Rule-trigger frames: collect best severity per frame_index, then sort
    best_sev: dict[int, str] = {}
    for t in rules_triggered:
        if t.frame_index is None or t.frame_index not in by_index:
            continue
        prev = best_sev.get(t.frame_index, "low")
        if _SEVERITY_ORDER.get(t.severity, 1) < _SEVERITY_ORDER.get(prev, 2):
            best_sev[t.frame_index] = t.severity

    for fidx, sev in sorted(best_sev.items(), key=lambda kv: (_SEVERITY_ORDER.get(kv[1], 1), kv[0])):
        if len(selected) >= max_frames:
            break
        _add(by_index[fidx], f"rule_trigger:severity={sev}")
    if len(selected) >= max_frames:
        return _sorted(selected)

    # 3. High OCR density (chars per frame, descending; tiebreak ascending index)
    density = sorted(
        [
            (
                f.frame_index,
                sum(
                    len(item.text)
                    for item in split_fine_print(
                        ocr_by_frame.get(f.frame_index, []),
                        frame_path=f.path,
                    )[0]
                ),
            )
            for f in kept_frames
            if f.frame_index not in selected
        ],
        key=lambda x: (-x[1], x[0]),
    )
    for fidx, char_count in density:
        if len(selected) >= max_frames:
            break
        if char_count > 0:
            _add(by_index[fidx], f"high_ocr_density:{char_count}")
    if len(selected) >= max_frames:
        return _sorted(selected)

    # 4. Even time distribution: greedy — pick frame furthest from any selected time
    selected_times = sorted(f.time_ms for f, _ in selected.values())
    remaining = [f for f in kept_frames if f.frame_index not in selected]

    while remaining and len(selected) < max_frames:
        # Distance for each candidate = min distance to any already-selected time
        max_dist = max(
            min(abs(f.time_ms - t) for t in selected_times) for f in remaining
        )
        # Among tied frames pick smallest frame_index (deterministic tiebreak)
        best = min(
            (f for f in remaining if min(abs(f.time_ms - t) for t in selected_times) == max_dist),
            key=lambda f: f.frame_index,
        )
        _add(best, "time_distributed")
        selected_times.append(best.time_ms)
        selected_times.sort()
        remaining = [f for f in remaining if f.frame_index not in selected]

    return _sorted(selected)


def _sorted(selected: dict[int, tuple[FrameAnalysis, str]]) -> list[tuple[FrameAnalysis, str]]:
    return sorted(selected.values(), key=lambda x: x[0].frame_index)


def build_evidence_bundle(
    *,
    ad_id: str,
    kept_frames: list[FrameAnalysis],
    transcript: WhisperTranscript,
    rules_triggered: list[RuleTrigger],
    ocr_by_frame: dict[int, list[OCRItem]] | None = None,
    paddlevl_by_frame: dict[int, PaddleVLOutput] | None = None,
    alignment_window_ms: int = 1500,
    max_frames: int = 12,
    metadata: dict | None = None,
) -> EvidenceBundle:
    """
    Build a compact evidence bundle for the VLM.

    When the number of kept frames exceeds *max_frames*, frames are selected
    deterministically per the H.1 priority order.
    """
    ocr_by_frame = ocr_by_frame or {}
    paddlevl_by_frame = paddlevl_by_frame or {}

    selected = _select_frames(
        kept_frames=kept_frames,
        rules_triggered=rules_triggered,
        ocr_by_frame=ocr_by_frame,
        max_frames=max_frames,
    )

    summaries: list[FrameSummary] = []
    for frame, reason in selected:
        ocr_items, fine_print_ocr_items = split_fine_print(
            ocr_by_frame.get(frame.frame_index, []),
            frame_path=frame.path,
        )
        paddlevl = paddlevl_by_frame.get(frame.frame_index)
        nearby = align_transcript_to_frame(transcript, frame.time_ms, alignment_window_ms)
        summaries.append(
            FrameSummary(
                frame_index=frame.frame_index,
                time_ms=frame.time_ms,
                path=frame.path,
                ocr_items=ocr_items,
                fine_print_ocr_items=fine_print_ocr_items,
                paddlevl_output=paddlevl,
                transcript_nearby=nearby,
                selection_reason=reason,
            )
        )

    return EvidenceBundle(
        ad_id=ad_id,
        frame_summaries=summaries,
        frame_image_paths=[s.path for s in summaries],
        full_transcript=transcript,
        rules_triggered=rules_triggered,
        metadata=metadata or {},
    )
