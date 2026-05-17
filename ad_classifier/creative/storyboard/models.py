from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ad_classifier.models.common import EvidenceItem, StrictModel


class StoryboardShot(StrictModel):
    shot_index: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    representative_frame_index: int | None = Field(default=None, ge=0)
    representative_frame_path: str | None = None
    transition: str
    camera_motion: str
    shot_type: str
    camera_angle: str
    on_screen_text: list[str] = Field(default_factory=list)
    voiceover: str | None = None
    emotional_beat: str
    narrative_function: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class Storyboard(StrictModel):
    ad_id: str
    generated_at: datetime
    json_path: str
    html_path: str
    shot_count: int = Field(ge=0)
    method: str
    shots: list[StoryboardShot] = Field(default_factory=list)
