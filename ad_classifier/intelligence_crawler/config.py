"""Configuration for the intelligence crawler.

Loaded from ``intelligence_crawler.yaml`` (kept separate from ``config.yaml`` so this
dedicated subsystem evolves independently). Secrets are referenced by env-var name
and read from ``.env.local`` — never stored here. All sources are disabled by default,
so an unconfigured install is a safe no-op.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ad_classifier.intelligence_crawler.models import IntelSource, Market, Tier
from ad_classifier.intelligence_crawler.tiers import CANONICAL_SOURCE_TIERS


class SourceConfig(BaseModel):
    """One configured source; unknown keys are rejected to catch configuration typos."""

    model_config = ConfigDict(extra="forbid")

    id: str
    brand: str
    source_type: str
    tier: Tier = "B"
    market: Market = "US"
    enabled: bool = False
    url: str | None = None
    platform: str | None = None
    platform_id: str | None = None
    poll_interval_hours: float = Field(default=12.0, gt=0)
    allowed_domains: list[str] = Field(default_factory=list)
    # Adapter-specific opaque settings (e.g. api_key_env, mock items). Kept as an open
    # dict so a new adapter can carry its own config without touching this schema.
    config: dict = Field(default_factory=dict)
    notes: str | None = None

    @model_validator(mode="after")
    def enforce_canonical_tier(self) -> SourceConfig:
        canonical = CANONICAL_SOURCE_TIERS.get(self.source_type)
        if canonical is not None and self.tier != canonical:
            object.__setattr__(self, "tier", canonical)
        return self

    def to_source(self) -> IntelSource:
        return IntelSource(
            id=self.id,
            brand_name=self.brand,
            market=self.market,
            source_type=self.source_type,
            tier=self.tier,
            url=self.url,
            platform=self.platform,
            platform_id=self.platform_id,
            enabled=self.enabled,
            poll_interval_hours=self.poll_interval_hours,
            allowed_domains=list(self.allowed_domains),
            config=dict(self.config),
            notes=self.notes,
        )


class HttpConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    respect_robots_txt: bool = True
    timeout_s: float = Field(default=12.0, gt=0)
    rate_limit_per_minute: int = Field(default=20, ge=1)
    max_page_bytes: int = Field(default=2_000_000, ge=50_000)
    user_agent: str = "ARGUS-IntelligenceCrawler/0.1 (+local analyst tool)"


class DetectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Newly-seen items older than this (by published date) are recorded as backfill, not
    # emitted as live "new ad" signals. Guards the cold-start back-catalog problem.
    new_signal_lookback_days: int = Field(default=30, ge=1)
    stale_after_days: int = Field(default=45, ge=1)


class ScoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # v1 3-term model: confidence = tier_weight + ad_likeness + corroboration (clamped).
    tier_weights: dict[str, float] = Field(
        default_factory=lambda: {"A": 0.55, "B": 0.35, "C": 0.15}
    )
    ad_likeness_bonus: float = Field(default=0.15, ge=0.0, le=1.0)
    corroboration_bonus: float = Field(default=0.2, ge=0.0, le=1.0)
    corroboration_cap: float = Field(default=0.4, ge=0.0, le=1.0)
    corroborated_min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    # Ad-likelihood gate: a *video* item must clear this to emit an ad signal (filters
    # channel content that isn't an ad — walkarounds, interviews, owner how-tos).
    min_ad_likelihood: float = Field(default=0.4, ge=0.0, le=1.0)
    ad_typical_max_seconds: int = Field(default=95, ge=1)  # :06/:15/:30/:60/:90 ads
    ad_longform_seconds: int = Field(default=180, ge=1)  # beyond this → unlikely an ad
    ad_like_terms: list[str] = Field(
        default_factory=lambda: [
            "ad",
            "advert",
            "commercial",
            "spot",
            "campaign",
            "launch",
            "introducing",
            "presents",
            "official",
            "trailer",
            "tvc",
        ]
    )


class WatchlistConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_graph_brands: bool = True
    entity_graph_db_path: Path | None = Path("./entity_graph.db")
    seed_brands: list[str] = Field(default_factory=list)


class IntelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    db_path: Path = Path("./intelligence_crawler.db")
    cache_dir: Path = Path("./data/intelligence_crawler_cache")
    market: Market = "US"
    mutation_api_key_env: str | None = "INTELLIGENCE_CRAWLER_API_KEY"
    http: HttpConfig = Field(default_factory=HttpConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    watchlist: WatchlistConfig = Field(default_factory=WatchlistConfig)
    sources: list[SourceConfig] = Field(default_factory=list)

    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources if s.enabled]

    def source_by_id(self, source_id: str) -> SourceConfig | None:
        return next((s for s in self.sources if s.id == source_id), None)


def load_intel_config(path: Path | None) -> IntelConfig:
    """Load config, resolving relative paths against the yaml file's directory."""
    if path is None:
        return IntelConfig()
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return IntelConfig()
    data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    config = IntelConfig.model_validate(data)
    return _resolve_paths(config, resolved.parent)


def _resolve_paths(config: IntelConfig, base: Path) -> IntelConfig:
    updates: dict[str, object] = {}
    if not config.db_path.is_absolute():
        updates["db_path"] = (base / config.db_path).resolve()
    if not config.cache_dir.is_absolute():
        updates["cache_dir"] = (base / config.cache_dir).resolve()
    graph_path = config.watchlist.entity_graph_db_path
    if graph_path is not None and not graph_path.is_absolute():
        updates["watchlist"] = config.watchlist.model_copy(
            update={"entity_graph_db_path": (base / graph_path).resolve()}
        )
    return config.model_copy(update=updates) if updates else config
