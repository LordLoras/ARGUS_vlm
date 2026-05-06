from __future__ import annotations

from pydantic import Field

from ad_classifier.models.common import StrictModel


class PaddleVLGatingConfig(StrictModel):
    force_all: bool = False
    mean_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    min_item_confidence_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    dense_text_char_threshold: int = Field(default=500, ge=0)
    short_fragment_count_threshold: int = Field(default=20, ge=0)
    short_fragment_max_len: int = Field(default=3, ge=0)


class PaddleVLOutput(StrictModel):
    frame_index: int = Field(ge=0)
    time_ms: int = Field(ge=0)
    raw_text: str | None = None   # captured stdout
    parsed: dict | None = None    # JSON-parsed from raw_text
    parse_ok: bool = False
    stderr: str | None = None
    engine: str = "paddlevl"
