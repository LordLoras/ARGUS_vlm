from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceSource = Literal["ocr", "paddlevl", "transcript", "visual", "rule", "vlm"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(StrictModel):
    time_ms: int = Field(ge=0)
    frame_index: int | None = Field(default=None, ge=0)
    source: EvidenceSource
    text: str
    bbox: list[float] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str | None = None
