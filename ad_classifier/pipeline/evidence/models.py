from __future__ import annotations

from pathlib import Path

from pydantic import Field

from ad_classifier.ingest.models import TranscriptSegment, WhisperTranscript
from ad_classifier.models.common import StrictModel
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.paddlevl.models import PaddleVLOutput
from ad_classifier.pipeline.rules.models import RuleTrigger


class FrameSummary(StrictModel):
    frame_index: int = Field(ge=0)
    time_ms: int = Field(ge=0)
    path: Path
    ocr_items: list[OCRItem] = Field(default_factory=list)
    broadcast_overlay_ocr_items: list[OCRItem] = Field(default_factory=list)
    fine_print_ocr_items: list[OCRItem] = Field(default_factory=list)
    paddlevl_output: PaddleVLOutput | None = None
    transcript_nearby: list[TranscriptSegment] = Field(default_factory=list)
    # Why this frame was included in the bundle (H.1 selection reason)
    selection_reason: str | None = None


class EvidenceBundle(StrictModel):
    ad_id: str
    # All analysed frame summaries (subset of kept frames, capped by max_frames)
    frame_summaries: list[FrameSummary]
    # Paths to send to the VLM (same order as frame_summaries)
    frame_image_paths: list[Path]
    full_transcript: WhisperTranscript
    rules_triggered: list[RuleTrigger] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
