from __future__ import annotations

from pathlib import Path

from pydantic import Field

from ad_classifier.models.common import StrictModel


class PreprocessConfig(StrictModel):
    # Grayscale std-dev below this → frame considered blank/near-blank
    blank_std_threshold: float = Field(default=10.0, ge=0.0)
    # Laplacian variance below this → frame considered blurry
    blur_laplacian_threshold: float = Field(default=100.0, ge=0.0)
    # Hamming distance below this → phash counts as "same" (0..64 for 8x8 phash)
    phash_hamming_threshold: int = Field(default=8, ge=0)
    # Mean absolute pixel diff (0..1) below this → frames count as visually unchanged
    pixel_diff_threshold: float = Field(default=0.05, ge=0.0, le=1.0)


class FrameAnalysis(StrictModel):
    frame_index: int = Field(ge=0)
    time_ms: int = Field(ge=0)
    path: Path
    phash: str | None = None
    blur_score: float | None = None   # Laplacian variance; higher = sharper
    blank_std: float | None = None    # grayscale std dev; lower = more blank
    pixel_diff: float | None = None   # mean abs diff (0..1) from previous kept frame
    is_blank: bool = False
    is_blurry: bool = False
    kept: bool = True
    drop_reason: str | None = None
    # Hook for OCR-aware refinement: set after OCR stage to override drop decision
    ocr_override: bool = False


class PreprocessResult(StrictModel):
    frames: list[FrameAnalysis]

    @property
    def kept_frames(self) -> list[FrameAnalysis]:
        return [f for f in self.frames if f.kept]

    @property
    def dropped_frames(self) -> list[FrameAnalysis]:
        return [f for f in self.frames if not f.kept]
