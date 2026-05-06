from __future__ import annotations

from pathlib import Path

from ad_classifier.dedup.phash import hamming_distance
from ad_classifier.pipeline.preprocess.analysis import (
    compute_blank_std,
    compute_blur_score,
    compute_phash,
    compute_pixel_diff,
)
from ad_classifier.pipeline.preprocess.models import (
    FrameAnalysis,
    PreprocessConfig,
    PreprocessResult,
)


class _FrameInput:
    """Minimal duck-type accepted by preprocess_frames."""

    __slots__ = ("frame_index", "time_ms", "path")

    def __init__(self, frame_index: int, time_ms: int, path: Path) -> None:
        self.frame_index = frame_index
        self.time_ms = time_ms
        self.path = path


def preprocess_frames(
    frames: list,  # list[IngestFrame | ManifestFrame-like]; any object with frame_index/time_ms/path
    config: PreprocessConfig | None = None,
) -> PreprocessResult:
    """
    Analyse and filter frames for the classification pipeline.

    Keyframe retention policy (applied in order of priority):
      1. First and last frames are always kept.
      2. Blank frames (low grayscale std-dev) are dropped.
      3. Blurry frames (low Laplacian variance) are dropped.
      4. Frames whose phash AND pixel-diff are both below threshold vs the
         previous kept frame are dropped as near-duplicates.
      5. All other frames are kept.

    ``ocr_override=True`` on a FrameAnalysis signals a later OCR-aware pass
    that the frame should be reconsidered for retention.
    """
    if config is None:
        config = PreprocessConfig()

    if not frames:
        return PreprocessResult(frames=[])

    n = len(frames)
    analyzed: list[FrameAnalysis] = []
    last_kept: FrameAnalysis | None = None

    for i, frame in enumerate(frames):
        is_first = i == 0
        is_last = i == n - 1

        path = Path(frame.path) if not isinstance(frame.path, Path) else frame.path

        blank_std = compute_blank_std(path)
        blur_score = compute_blur_score(path)
        phash = compute_phash(path)

        is_blank = blank_std < config.blank_std_threshold
        # Only test blur on non-blank frames (solid images have zero Laplacian too)
        is_blurry = (not is_blank) and blur_score < config.blur_laplacian_threshold

        pixel_diff: float | None = None
        if last_kept is not None:
            pixel_diff = compute_pixel_diff(last_kept.path, path)

        kept = True
        drop_reason: str | None = None

        if is_first or is_last:
            # Always retain boundary frames regardless of quality signals
            pass
        elif is_blank:
            kept = False
            drop_reason = "blank"
        elif is_blurry:
            kept = False
            drop_reason = "blurry"
        elif (
            last_kept is not None
            and phash is not None
            and last_kept.phash is not None
            and pixel_diff is not None
        ):
            dist = hamming_distance(phash, last_kept.phash)
            if (
                dist < config.phash_hamming_threshold
                and pixel_diff < config.pixel_diff_threshold
            ):
                kept = False
                drop_reason = f"phash_dup:hamming={dist}"

        fa = FrameAnalysis(
            frame_index=frame.frame_index,
            time_ms=frame.time_ms,
            path=path,
            phash=phash,
            blur_score=blur_score,
            blank_std=blank_std,
            pixel_diff=pixel_diff,
            is_blank=is_blank,
            is_blurry=is_blurry,
            kept=kept,
            drop_reason=drop_reason,
        )
        analyzed.append(fa)

        if kept:
            last_kept = fa

    return PreprocessResult(frames=analyzed)
