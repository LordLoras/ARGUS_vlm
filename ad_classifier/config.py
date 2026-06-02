from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

VLMMode = Literal["local", "remote", "frontier"]
AgentInheritMode = Literal["active", "local", "remote", "frontier"]


class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data_root: Path = Path("./data")
    uploads: Path = Path("./data/uploads")
    frames: Path = Path("./data/frames")
    audio: Path = Path("./data/audio")
    whisper: Path = Path("./data/whisper")
    out: Path = Path("./data/out")
    sqlite_path: Path = Path("./ad_classifier.db")
    entity_graph_path: Path = Path("./entity_graph.db")
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


class PostOCRDedupConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    skip_on_exact: bool = True
    candidate_phash_distance: int = Field(default=16, ge=0)
    per_frame_phash_distance: int = Field(default=6, ge=0)
    duration_tolerance_ms: int = Field(default=1500, ge=0)
    min_frame_match_ratio: float = Field(default=0.90, ge=0.0, le=1.0)
    min_text_similarity: float = Field(default=0.90, ge=0.0, le=1.0)
    min_transcript_similarity: float = Field(default=0.88, ge=0.0, le=1.0)
    min_signature_similarity: float = Field(default=0.82, ge=0.0, le=1.0)
    min_text_chars: int = Field(default=80, ge=0)
    max_candidates: int = Field(default=25, ge=1)


class DedupConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skip_on_exact: bool = True
    skip_on_near_duplicate: bool = False
    phash_distance_threshold: int = Field(default=4, ge=0)
    post_ocr: PostOCRDedupConfig = Field(default_factory=PostOCRDedupConfig)


class OCRConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    backend: Literal["paddleocr"] = "paddleocr"
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

    enabled: bool = False
    command: str = (
        "paddlex --pipeline PaddleOCR-VL-native.yaml" " --input {image_path} --output {output_dir}"
    )
    timeout_s: float = Field(default=60.0, ge=0.0)
    gating: PaddleVLGatingConfig = Field(default_factory=PaddleVLGatingConfig)


class GLMOCREndpointConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint: str = "http://127.0.0.1:5050/v1"
    model: str = "glm-ocr"
    api_key_env: str | None = None
    timeout_s: float = Field(default=120.0, ge=0.0)
    max_retries: int = Field(default=1, ge=0)
    retry_delay_s: float = Field(default=1.0, ge=0.0)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=64)
    stream: bool = True


class GLMOCREndpointDefaults:
    LOCAL = GLMOCREndpointConfig(
        endpoint="http://127.0.0.1:5050/v1",
        model="glm-ocr",
        api_key_env=None,
        timeout_s=120.0,
        max_retries=1,
        retry_delay_s=1.0,
        temperature=0.0,
        max_tokens=2048,
        stream=True,
    )
    REMOTE = GLMOCREndpointConfig(
        endpoint="https://your-openai-compatible-glm-ocr.example/v1",
        model="glm-ocr",
        api_key_env="GLM_OCR_API_KEY",
        timeout_s=120.0,
        max_retries=1,
        retry_delay_s=1.0,
        temperature=0.0,
        max_tokens=2048,
        stream=True,
    )


class GLMOCRConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    mode: Literal["local", "remote"] = "local"
    prompt: str = (
        "Transcribe all visible text exactly. Preserve line breaks and reading order. "
        "Do not summarize or infer."
    )
    image_max_dim: int = Field(default=1024, ge=128, le=2048)
    include_in_search: bool = True
    include_in_vlm_bundle: bool = False
    run_on_text_frames: bool = True
    min_ocr_chars: int = Field(default=100, ge=0)
    run_when_ocr_disabled: bool = True
    max_frames_per_ad: int = Field(default=12, ge=1)
    gating: PaddleVLGatingConfig = Field(default_factory=PaddleVLGatingConfig)
    local: GLMOCREndpointConfig = Field(
        default_factory=lambda: GLMOCREndpointDefaults.LOCAL.model_copy()
    )
    remote: GLMOCREndpointConfig = Field(
        default_factory=lambda: GLMOCREndpointDefaults.REMOTE.model_copy()
    )
    endpoint: GLMOCREndpointConfig = Field(default_factory=GLMOCREndpointConfig)

    @model_validator(mode="after")
    def _resolve_mode_endpoint(self) -> GLMOCRConfig:
        if self.mode == "local":
            self.endpoint = self.local.model_copy()
        else:
            self.endpoint = self.remote.model_copy()
        return self


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

    enabled: bool = True
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
    use_campaign_suggestions: bool = True
    min_campaign_signal_confidence: float = Field(default=0.80, ge=0.0, le=1.0)
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


class PublicApiConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    api_key: str | None = None


class APIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    upload: UploadConfig = Field(default_factory=UploadConfig)
    public: PublicApiConfig = Field(default_factory=PublicApiConfig)


class WorkerConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    poll_interval_ms: int = Field(default=1000, ge=50)
    concurrency: int = Field(default=1, ge=1)


class VLMEndpointConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint: str = "http://127.0.0.1:1234/v1"
    model: str = "argus/vlm"
    api_key_env: str | None = None
    timeout_s: float = Field(default=240.0, ge=0.0)
    max_retries: int = Field(default=2, ge=0)
    retry_delay_s: float = Field(default=2.0, ge=0.0)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=64)
    enable_thinking: bool = False
    response_format: Literal["json_object", "json_schema"] = "json_object"
    stream: bool = True


class VLMEndpointDefaults:
    LOCAL = VLMEndpointConfig(
        endpoint="http://127.0.0.1:1234/v1",
        model="Qwen3.6-27B-Q4_K_M",
        api_key_env=None,
        timeout_s=600.0,
        max_retries=2,
        retry_delay_s=2.0,
        temperature=0.1,
        max_tokens=8192,
        enable_thinking=False,
        response_format="json_object",
        stream=True,
    )
    REMOTE = VLMEndpointConfig(
        endpoint="https://api.openai.com/v1",
        model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        timeout_s=120.0,
        max_retries=2,
        retry_delay_s=2.0,
        temperature=0.3,
        max_tokens=8192,
        enable_thinking=False,
        response_format="json_schema",
        stream=True,
    )
    FRONTIER = VLMEndpointConfig(
        endpoint="https://openrouter.ai/api/v1",
        model="openrouter/auto",
        api_key_env="OPENROUTER_API_KEY",
        timeout_s=180.0,
        max_retries=2,
        retry_delay_s=2.0,
        temperature=0.2,
        max_tokens=8192,
        enable_thinking=False,
        response_format="json_schema",
        stream=True,
    )


class VLMComplexityConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    ocr_item_threshold: int = Field(default=120, ge=1)
    ocr_char_threshold: int = Field(default=1400, ge=1)
    max_frame_ocr_chars_threshold: int = Field(default=180, ge=1)
    transcript_char_threshold: int = Field(default=1200, ge=1)
    kept_frame_threshold: int = Field(default=24, ge=1)
    cleanup_max_tokens: int = Field(default=4096, ge=64)
    verifier_max_tokens: int = Field(default=8192, ge=64)
    self_correction_max_tokens: int = Field(default=4096, ge=64)


class VLMConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mode: VLMMode = "local"
    prompt_profile: Literal["auto", "standard", "frontier_strict"] = "auto"
    prompt_overrides: dict[str, str] = Field(default_factory=dict)
    max_frames_in_bundle: int = Field(default=12, ge=1)
    image_max_dim: int = Field(default=512, ge=128, le=2048)
    enable_ocr_cleanup_pass: bool = True
    enable_self_correction: bool = True
    enable_post_validation: bool = True
    enable_visual_verify: bool = False
    complexity: VLMComplexityConfig = Field(default_factory=VLMComplexityConfig)
    local: VLMEndpointConfig = Field(default_factory=lambda: VLMEndpointDefaults.LOCAL.model_copy())
    remote: VLMEndpointConfig = Field(
        default_factory=lambda: VLMEndpointDefaults.REMOTE.model_copy()
    )
    frontier: VLMEndpointConfig = Field(
        default_factory=lambda: VLMEndpointDefaults.FRONTIER.model_copy()
    )
    endpoint: VLMEndpointConfig = Field(default_factory=VLMEndpointConfig)

    @model_validator(mode="after")
    def _resolve_mode_endpoint(self) -> VLMConfig:
        if self.mode == "local":
            self.endpoint = self.local.model_copy()
        elif self.mode == "remote":
            self.endpoint = self.remote.model_copy()
        else:
            self.endpoint = self.frontier.model_copy()
        return self

    def resolved_prompt_profile(self) -> str:
        if self.prompt_profile == "auto":
            return "frontier_strict" if self.mode == "frontier" else "standard"
        return self.prompt_profile

    def prompt_override_for(self, profile: str) -> str | None:
        override = self.prompt_overrides.get(profile)
        return override if isinstance(override, str) and override.strip() else None


class AgentEndpointConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    endpoint: str | None = None
    model: str | None = None
    api_key_env: str | None = None
    timeout_s: float | None = None
    max_retries: int | None = None
    retry_delay_s: float | None = None
    stream: bool | None = None


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inherit_vlm: bool = True
    inherit_vlm_mode: AgentInheritMode = "active"
    endpoint: AgentEndpointConfig = Field(default_factory=AgentEndpointConfig)
    max_iterations: int = Field(default=8, ge=1, le=32)
    list_max_rows: int = Field(default=50, ge=1, le=500)
    sql_readonly_max_rows: int = Field(default=50, ge=1, le=500)
    sql_statement_timeout_s: float = Field(default=5.0, ge=0.1)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=64)

    @property
    def effective_mode(self) -> str:
        if not self.inherit_vlm:
            return "independent"
        return f"inherited:{self.inherit_vlm_mode}"


class CreativePanelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inherit_vlm: bool = True
    endpoint: AgentEndpointConfig = Field(default_factory=AgentEndpointConfig)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8192, ge=64)

    @property
    def effective_mode(self) -> str:
        return "inherited" if self.inherit_vlm else "independent"


class SearchConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text_min_score: float = Field(default=0.20, ge=0.0, le=1.0)
    visual_min_score: float = Field(default=0.03, ge=-1.0, le=1.0)
    visual_hybrid_min_score: float = Field(default=0.08, ge=-1.0, le=1.0)


class BrandProfilesConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    user_agent: str = (
        "ARGUS-VLM/0.1 (ad classifier; "
        "https://github.com/LordLoras/ARGUS_vlm)"
    )
    timeout_s: float = Field(default=10.0, ge=0.1)
    cache_days: int = Field(default=90, ge=1)
    max_candidates: int = Field(default=5, ge=1, le=10)
    max_parent_depth: int = Field(default=3, ge=0, le=5)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    paths: PathsConfig = Field(default_factory=PathsConfig)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    whisper: WhisperConfig = Field(default_factory=WhisperConfig)
    dedup: DedupConfig = Field(default_factory=DedupConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    paddlevl: PaddleVLConfig = Field(default_factory=PaddleVLConfig)
    glm_ocr: GLMOCRConfig = Field(default_factory=GLMOCRConfig)
    rules: RulesConfig = Field(default_factory=RulesConfig)
    vlm: VLMConfig = Field(default_factory=VLMConfig)
    text_embedder: TextEmbedderConfig = Field(default_factory=TextEmbedderConfig)
    image_embedder: ImageEmbedderConfig = Field(default_factory=ImageEmbedderConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    campaigns: CampaignsConfig = Field(default_factory=CampaignsConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    creative_panel: CreativePanelConfig = Field(default_factory=CreativePanelConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    brand_profiles: BrandProfilesConfig = Field(default_factory=BrandProfilesConfig)

    @model_validator(mode="after")
    def _resolve_ai_feature_endpoints(self) -> AppConfig:
        _resolve_agent_like_endpoint(
            self.agent.endpoint,
            _agent_inherit_endpoint(self.vlm, self.agent.inherit_vlm_mode),
            inherit_vlm=self.agent.inherit_vlm,
        )
        _resolve_agent_like_endpoint(
            self.creative_panel.endpoint,
            self.vlm.endpoint,
            inherit_vlm=self.creative_panel.inherit_vlm,
        )
        return self


def _agent_inherit_endpoint(vlm: VLMConfig, inherit_mode: AgentInheritMode) -> VLMEndpointConfig:
    if inherit_mode == "active":
        return vlm.endpoint
    return getattr(vlm, inherit_mode)


def _resolve_agent_like_endpoint(
    endpoint: AgentEndpointConfig,
    vlm_endpoint: VLMEndpointConfig,
    *,
    inherit_vlm: bool,
) -> None:
    if inherit_vlm:
        if endpoint.endpoint is None:
            endpoint.endpoint = vlm_endpoint.endpoint
        if endpoint.model is None:
            endpoint.model = vlm_endpoint.model
        if endpoint.api_key_env is None:
            endpoint.api_key_env = vlm_endpoint.api_key_env
        if endpoint.timeout_s is None:
            endpoint.timeout_s = vlm_endpoint.timeout_s
        if endpoint.max_retries is None:
            endpoint.max_retries = vlm_endpoint.max_retries
        if endpoint.retry_delay_s is None:
            endpoint.retry_delay_s = vlm_endpoint.retry_delay_s
        if endpoint.stream is None:
            endpoint.stream = vlm_endpoint.stream
        return

    if endpoint.endpoint is None:
        endpoint.endpoint = "http://127.0.0.1:1234/v1"
    if endpoint.model is None:
        endpoint.model = "argus/vlm"
    if endpoint.timeout_s is None:
        endpoint.timeout_s = 120.0
    if endpoint.max_retries is None:
        endpoint.max_retries = 2
    if endpoint.retry_delay_s is None:
        endpoint.retry_delay_s = 2.0
    if endpoint.stream is None:
        endpoint.stream = True


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
    from ad_classifier._env import configure_dotenv_path

    configure_dotenv_path(source.parent / ".env.local")
    return AppConfig.model_validate(data), source


def config_file_payload(config: AppConfig) -> dict[str, Any]:
    """Return config data suitable for writing to config.yaml.

    The active ``endpoint`` fields are derived from mode-specific presets at
    load time, so they are omitted from disk to keep the file editable and avoid
    duplicated stale endpoint copies.
    """

    payload = config.model_dump(
        mode="json",
        exclude={
            "vlm": {"endpoint"},
            "glm_ocr": {"endpoint"},
            "api": {"public": {"api_key"}},
        },
    )
    if payload.get("agent", {}).get("inherit_vlm") is True:
        payload["agent"]["endpoint"] = {}
    if payload.get("creative_panel", {}).get("inherit_vlm") is True:
        payload["creative_panel"]["endpoint"] = {}
    return payload


def save_config(config: AppConfig, path: Path) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = config_file_payload(config)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


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
