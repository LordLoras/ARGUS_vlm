from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ad_classifier.config import AppConfig
from ad_classifier.ingest.models import WhisperTranscript


class WhisperTranscriber(Protocol):
    def transcribe(self, audio_path: Path, output_path: Path) -> WhisperTranscript: ...


def build_transcriber(config: AppConfig, config_file: Path) -> WhisperTranscriber:
    if config.whisper.backend == "mock":
        from ad_classifier.ingest.whisper_mock import MockWhisperTranscriber

        return MockWhisperTranscriber()
    if config.whisper.backend == "whisper_cpp":
        from ad_classifier.ingest.whisper_cpp import WhisperCppTranscriber

        return WhisperCppTranscriber.from_config(config, config_file)
    if config.whisper.backend == "faster-whisper":
        from ad_classifier.ingest.whisper_faster import FasterWhisperTranscriber

        return FasterWhisperTranscriber.from_config(config)
    raise ValueError(f"Unsupported whisper backend: {config.whisper.backend}")
