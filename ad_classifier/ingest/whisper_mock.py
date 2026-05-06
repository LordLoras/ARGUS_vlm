from __future__ import annotations

from pathlib import Path

from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.ingest.transcript import write_transcript_json


class MockWhisperTranscriber:
    def __init__(self, transcript: WhisperTranscript | None = None) -> None:
        self.transcript = transcript or WhisperTranscript(
            language="en",
            text="",
            segments=[],
        )

    def transcribe(self, audio_path: Path, output_path: Path) -> WhisperTranscript:
        write_transcript_json(output_path, self.transcript)
        return self.transcript
