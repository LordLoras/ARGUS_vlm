from __future__ import annotations

import subprocess
from pathlib import Path

from ad_classifier.config import AppConfig, resolve_config_path
from ad_classifier.ingest.models import WhisperTranscript
from ad_classifier.ingest.transcript import load_transcript_json, write_transcript_json


class WhisperCppTranscriber:
    def __init__(
        self,
        *,
        command: Path,
        model_path: Path,
        language: str | None,
        use_gpu: bool,
        device: int,
        threads: int,
        extra_args: list[str] | None = None,
    ) -> None:
        self.command = command
        self.model_path = model_path
        self.language = language or "auto"
        self.use_gpu = use_gpu
        self.device = device
        self.threads = threads
        self.extra_args = extra_args or []

    @classmethod
    def from_config(cls, config: AppConfig, config_file: Path) -> WhisperCppTranscriber:
        whisper_cpp = config.whisper.whisper_cpp
        return cls(
            command=resolve_config_path(whisper_cpp.command, config_file),
            model_path=resolve_config_path(whisper_cpp.model_path, config_file),
            language=config.whisper.language,
            use_gpu=whisper_cpp.use_gpu,
            device=whisper_cpp.device,
            threads=whisper_cpp.threads,
            extra_args=whisper_cpp.extra_args,
        )

    def transcribe(self, audio_path: Path, output_path: Path) -> WhisperTranscript:
        if not self.command.exists():
            raise FileNotFoundError(f"whisper.cpp command not found: {self.command}")
        if not self.model_path.exists():
            raise FileNotFoundError(f"whisper.cpp model not found: {self.model_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_base = output_path.with_name(f"{output_path.stem}.raw")
        raw_json = output_path.with_name(f"{output_path.stem}.raw.json")
        if raw_json.exists():
            raw_json.unlink()

        cmd = [
            str(self.command),
            "-m",
            str(self.model_path),
            "-f",
            str(audio_path),
            "-oj",
            "-ojf",
            "-of",
            str(raw_base),
            "-l",
            self.language,
            "-t",
            str(self.threads),
        ]
        if self.use_gpu:
            cmd.extend(["-dev", str(self.device)])
        else:
            cmd.append("-ng")
        cmd.extend(self.extra_args)

        result = subprocess.run(
            cmd,
            cwd=self.command.parent,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"whisper.cpp failed: {stderr}")
        if not raw_json.exists():
            raise RuntimeError(f"whisper.cpp did not produce JSON output: {raw_json}")

        transcript = load_transcript_json(raw_json)
        write_transcript_json(output_path, transcript)
        return transcript
