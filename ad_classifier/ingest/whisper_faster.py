from __future__ import annotations

from pathlib import Path

from ad_classifier.config import AppConfig
from ad_classifier.ingest.models import TranscriptSegment, WhisperTranscript
from ad_classifier.ingest.transcript import write_transcript_json


class FasterWhisperTranscriber:
    def __init__(
        self,
        *,
        model_name: str,
        compute_type: str,
        language: str | None,
    ) -> None:
        self.model_name = model_name
        self.compute_type = compute_type
        self.language = language

    @classmethod
    def from_config(cls, config: AppConfig) -> FasterWhisperTranscriber:
        return cls(
            model_name=config.whisper.model,
            compute_type=config.whisper.compute_type,
            language=config.whisper.language,
        )

    def transcribe(self, audio_path: Path, output_path: Path) -> WhisperTranscript:
        from faster_whisper import WhisperModel  # noqa: PLC0415

        model = WhisperModel(self.model_name, device="cpu", compute_type=self.compute_type)
        segments_iter, info = model.transcribe(str(audio_path), language=self.language)
        segments = [
            TranscriptSegment(
                start_ms=int(round(segment.start * 1000)),
                end_ms=int(round(segment.end * 1000)),
                text=segment.text.strip(),
                confidence=None,
            )
            for segment in segments_iter
        ]
        transcript = WhisperTranscript(
            segments=segments,
            language=getattr(info, "language", self.language),
            text=" ".join(segment.text for segment in segments if segment.text).strip(),
        )
        write_transcript_json(output_path, transcript)
        return transcript
