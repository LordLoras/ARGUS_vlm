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


class DedupConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skip_on_exact: bool = True
    skip_on_near_duplicate: bool = False
    phash_distance_threshold: int = Field(default=4, ge=0)


class OCRConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    device: str = "cpu"
    lang: str = "en"


class PaddleVLGatingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    force_all: bool = False
    mean_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    min_item_confidence_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    dense_text_char_threshold: int = Field(default=500, ge=0)
    short_fragment_count_threshold: int = Field(default=20, ge=0)
    short_fragment_max_len: int = Field(default=3, ge=0)


class PaddleVLConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    command: str = (
        "paddlex --pipeline PaddleOCR-VL-native.yaml" " --input {image_path} --output {output_dir}"
    )
    timeout_s: float = Field(default=60.0, ge=0.0)
    gating: PaddleVLGatingConfig = Field(default_factory=PaddleVLGatingConfig)


class RulesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rules_path: Path | None = None  # None → built-in default_rules.yaml
    alignment_window_ms: int = Field(default=1500, ge=0)


class TextEmbedderConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    device: str = "cpu"
    batch_size: int = Field(default=32, ge=1)
    dim: int = Field(default=384, ge=1)


class ImageEmbedderConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "google/siglip2-base-patch16-224"
    device: str = "cpu"
    batch_size: int = Field(default=8, ge=1)
    dim: int = Field(default=768, ge=1)


class VectorStoreConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    backend: Literal["sqlite-vec"] = "sqlite-vec"
    text_dim: int = Field(default=384, ge=1)
    visual_dim: int = Field(default=768, ge=1)


class CampaignDiscoveryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lookback_days: int = Field(default=90, ge=1)
    min_cluster_size: int = Field(default=3, ge=2)
    min_mean_similarity: float = Field(default=0.75, ge=0.0, le=1.0)
    clusterer: Literal["hdbscan", "agglomerative"] = "hdbscan"
    name_template: str = "{brand} {month} {year}"


class CampaignsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    discover: CampaignDiscoveryConfig = Field(default_factory=CampaignDiscoveryConfig)


class UploadConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_bytes: int = Field(default=209_715_200, ge=1)
    allowed_mime: list[str] = Field(
        default_factory=lambda: ["video/mp4", "video/quicktime", "video/webm"]
    )


class APIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    upload: UploadConfig = Field(default_factory=UploadConfig)


class WorkerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    poll_interval_ms: int = Field(default=1000, ge=50)
    concurrency: int = Field(default=1, ge=1)


class VLMEndpointConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint: str = "http://127.0.0.1:1234/v1"
    model: str = "google/gemma-4-26b-a4b"
    api_key_env: str | None = None
    timeout_s: float = Field(default=240.0, ge=0.0)
    max_retries: int = Field(default=2, ge=0)
    retry_delay_s: float = Field(default=2.0, ge=0.0)


class VLMConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_frames_in_bundle: int = Field(default=12, ge=1)
    endpoint: VLMEndpointConfig = Field(default_factory=VLMEndpointConfig)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paths: PathsConfig = Field(default_factory=PathsConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    whisper: WhisperConfig = Field(default_factory=WhisperConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    paddlevl: PaddleVLConfig = Field(default_factory=PaddleVLConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    vlm: VLMConfig = Field(default_factory=VLMConfig)
    text_embedder: TextEmbedderConfig = Field(default_factory=TextEmbedderConfig)
    image_embedder: ImageEmbedderConfig = Field(default_factory=ImageEmbedderConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    campaigns: CampaignsConfig = Field(default_factory=CampaignsConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)


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
