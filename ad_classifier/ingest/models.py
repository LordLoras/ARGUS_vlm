from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from ad_classifier.models.common import StrictModel

IngestStage = Literal["probe", "frames", "audio", "whisper", "manifest", "persist"]


class VideoMetadata(StrictModel):
    duration_ms: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    fps: float | None = Field(default=None, ge=0)
    video_codec: str | None = None
    audio_codec: str | None = None

    @property
    def has_audio(self) -> bool:
        return self.audio_codec is not None


class IngestFrame(StrictModel):
    frame_index: int = Field(ge=0)
    time_ms: int = Field(ge=0)
    path: Path


class TranscriptSegment(StrictModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class WhisperTranscript(StrictModel):
    segments: list[TranscriptSegment] = Field(default_factory=list)
    language: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    text: str = ""


class ManifestFrame(StrictModel):
    frame_index: int = Field(ge=0)
    time_ms: int = Field(ge=0)
    path: str


class Manifest(StrictModel):
    ad_id: str | None = None
    frame_interval_ms: int = Field(ge=1)
    frames: list[ManifestFrame]
    transcript: WhisperTranscript


class IngestEvent(StrictModel):
    stage: IngestStage
    message: str
    done: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    reused: bool = False


class IngestArtifacts(StrictModel):
    ad_id: str
    source_path: Path
    metadata: VideoMetadata
    frames_dir: Path
    frames: list[IngestFrame]
    audio_path: Path | None
    whisper_path: Path
    manifest_path: Path
    transcript: WhisperTranscript
    events: list[IngestEvent] = Field(default_factory=list)
