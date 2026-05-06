from __future__ import annotations

from pathlib import Path
from typing import Any

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


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paths: PathsConfig = Field(default_factory=PathsConfig)


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
