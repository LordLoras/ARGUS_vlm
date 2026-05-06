from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data_root: Path = Path("./data")
    uploads: Path = Path("./data/uploads")
    frames: Path = Path("./data/frames")
    audio: Path = Path("./data/audio")
    whisper: Path = Path("./data/whisper")
    out: Path = Path("./data/out")
    sqlite_path: Path = Path("./ad_classifier.db")
    qdrant_path: Path = Path("./qdrant_db")


class IngestConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    frame_interval_ms: int = Field(default=500, ge=1)
    audio_sample_rate: int = Field(default=16000, ge=8000)


class WhisperCppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    command: Path = Path("./tools/whisper.cpp/whisper-cli.exe")
    model_path: Path = Path("./models/whisper/ggml-tiny.en.bin")
    use_gpu: bool = True
    device: int = Field(default=0, ge=0)
    threads: int = Field(default=8, ge=1)
    extra_args: list[str] = Field(default_factory=list)


class WhisperConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    backend: Literal["whisper_cpp", "faster-whisper", "mock"] = "whisper_cpp"
    model: str = "tiny.en"
    compute_type: str = "int8"
    language: str | None = None
    whisper_cpp: WhisperCppConfig = Field(default_factory=WhisperCppConfig)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paths: PathsConfig = Field(default_factory=PathsConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    whisper: WhisperConfig = Field(default_factory=WhisperConfig)


def default_config_path(cwd: Path | None = None) -> Path:
    base = cwd or Path.cwd()
    local_config = base / "config.yaml"
    if local_config.exists():
        return local_config
    return base / "config.example.yaml"


def load_config(path: Path | None = None) -> tuple[AppConfig, Path]:
    source = path or default_config_path()
    source = source.expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"Config file not found: {source}")

    data: dict[str, Any] = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data), source


def resolve_config_path(value: Path, config_file: Path) -> Path:
    path = value.expanduser()
    if path.is_absolute():
        return path.resolve()
    return (config_file.parent / path).resolve()


def resolve_sqlite_path(config_path: Path | None = None, override: Path | None = None) -> Path:
    if override is not None:
        return override.expanduser().resolve()

    config, source = load_config(config_path)
    return resolve_config_path(config.paths.sqlite_path, source)
