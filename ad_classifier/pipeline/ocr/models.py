from __future__ import annotations

from pathlib import Path

from pydantic import Field

from ad_classifier.models.common import StrictModel


class FrameRef(StrictModel):
    """Minimal frame descriptor passed to OCR engines."""

    frame_index: int = Field(ge=0)
    time_ms: int = Field(ge=0)
    path: Path


class OCRItem(StrictModel):
    frame_index: int = Field(ge=0)
    time_ms: int = Field(ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    # Flattened polygon: [x1,y1, x2,y2, x3,y3, x4,y4] or None
    bbox: list[float] | None = None
    engine: str
