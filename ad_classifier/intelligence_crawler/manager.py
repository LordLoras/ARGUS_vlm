"""Facade over the intelligence crawler for API/CLI callers (mirrors EntityGraphManager).

Holds the config + a single repository, and exposes read methods (read-only connection)
plus a crawl trigger. Keeps routers thin and the DB wiring in one place.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import structlog

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.diagnostics import safe_traceback
from ad_classifier.intelligence_crawler.digest import build_digest
from ad_classifier.intelligence_crawler.ids import new_run_id
from ad_classifier.intelligence_crawler.models import (
    CrawlRunSummary,
    DigestEntry,
    IntelAdapterDescriptor,
    IntelBrandOverview,
    IntelResourceView,
    IntelSignal,
    IntelSource,
    IntelSourceStatus,
    Tier,
    WatchedBrand,
)
from ad_classifier.intelligence_crawler.repository import IntelRepository
from ad_classifier.intelligence_crawler.runner import IntelRunner
from ad_classifier.intelligence_crawler.sources.base import available_source_types
from ad_classifier.intelligence_crawler.tiers import canonical_tier
from ad_classifier.intelligence_crawler.watchlist import build_watchlist

logger = structlog.get_logger(__name__)

ADAPTER_DESCRIPTORS: dict[str, IntelAdapterDescriptor] = {
    "meta_ad_library_ui": IntelAdapterDescriptor(
        source_type="meta_ad_library_ui",
        label="Meta Ad Library",
        target_label="Meta advertiser Page ID",
        target_placeholder="Toyota Facebook Page ID, e.g. 197052454200",
        helper_text=(
            "Public Meta Ad Library monitoring for a Facebook advertiser Page ID, not a "
            "single ad or campaign id. Stores visible cards, copy, library ids, screenshots, "
            "image URLs, exposed video URLs, and multiple-version counts when shown."
        ),
        default_tier="A",
        platform="meta",
        requires_platform_id=True,
        config={
            "active_status": "active",
            "sort_mode": "relevancy_monthly_grouped",
            "sort_direction": "desc",
            "scrolls": 20,
            "max_cards": 250,
            "wait_ms": 1800,
            "stop_after_no_new": 3,
        },
        provides=[
            "Meta library IDs",
            "card screenshots",
            "visible ad copy",
            "image URLs",
            "video URLs when exposed",
            "started-running dates",
            "multiple-version counts",
        ],
    ),
    "youtube_channel": IntelAdapterDescriptor(
        source_type="youtube_channel",
        label="YouTube channel",
        target_label="Channel ID",
        target_placeholder="UC...",
        helper_text="Official channel monitoring through public feeds and video metadata.",
        default_tier="C",
        platform="youtube",
        requires_platform_id=True,
        provides=["video ids", "titles", "descriptions", "publish dates", "thumbnails"],
    ),
    "rss": IntelAdapterDescriptor(
        source_type="rss",
        label="RSS / newsroom feed",
        target_label="Feed URL",
        target_placeholder="https://pressroom.toyota.com/product/feed/",
        helper_text="Robots-gated feed monitoring for newsroom and trade-press releases.",
        default_tier="C",
        requires_url=True,
        provides=["article URLs", "titles", "descriptions", "publish dates"],
    ),
    "google_atc": IntelAdapterDescriptor(
        source_type="google_atc",
        label="Google Ads Transparency",
        target_label="ATC advertiser ID",
        target_placeholder="ATC advertiser id, e.g. AR03692565387905335297",
        helper_text=(
            "Ads Transparency Center monitoring for a US advertiser id (the AR... id in the "
            "adstransparency.google.com/advertiser/<id> URL, not a single creative). Lists the "
            "advertiser's US creatives with creative ids, formats, first/last-shown dates, and "
            "preview links."
        ),
        default_tier="B",
        platform="google",
        requires_platform_id=True,
        config={
            "page_size": 40,
            "max_pages": 0,
            "preview_enrichment": True,
            "preview_enrichment_limit": 40,
        },
        provides=[
            "ATC creative IDs",
            "advertiser name",
            "ad format",
            "first/last-shown dates",
            "preview URLs",
            "image URLs",
            "YouTube video IDs",
            "video thumbnails",
        ],
    ),
    "mock": IntelAdapterDescriptor(
        source_type="mock",
        label="Mock source",
        target_label="Fixture config",
        target_placeholder="Configured in JSON",
        helper_text="Offline deterministic adapter for tests and demos.",
        default_tier="A",
        provides=["configured fixture resources"],
    ),
}


class IntelManager:
    def __init__(self, config: IntelConfig, *, repo: IntelRepository | None = None) -> None:
        self.config = config
        self.repo = repo or IntelRepository(config.db_path)
        self.seed_config_sources()

    def seed_config_sources(self) -> None:
        """Persist YAML seed sources so read endpoints see them before the first crawl."""
        if not self.config.sources:
            return
        with self.repo.connect() as conn:
            self.repo.seed_sources(conn, [source.to_source() for source in self.config.sources])
            conn.commit()

    def list_signals(
        self,
        *,
        brand: str | None = None,
        since: datetime | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[IntelSignal]:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.list_signals(
                conn, brand=brand, since=since, status=status, limit=limit
            )

    def get_signal(self, signal_id: str) -> IntelSignal | None:
        with self.repo.connect(readonly=True) as conn:
            signal = self.repo.get_signal(conn, signal_id)
            if signal is None:
                return None
            evidence = self.repo.evidence_for(conn, signal_id)
        return signal.model_copy(update={"evidence": evidence})

    def digest(self, *, since: datetime | None, limit: int = 200) -> list[DigestEntry]:
        return build_digest(self.repo, since=since, limit=limit)

    def watchlist(self) -> list[WatchedBrand]:
        return build_watchlist(self.config)

    def source_types(self) -> list[str]:
        return available_source_types()

    def adapters(self) -> list[IntelAdapterDescriptor]:
        descriptors = []
        for source_type in available_source_types():
            descriptor = ADAPTER_DESCRIPTORS.get(source_type)
            if descriptor is None:
                descriptor = IntelAdapterDescriptor(
                    source_type=source_type,
                    label=source_type.replace("_", " ").title(),
                    target_label="Target",
                    target_placeholder="Source target",
                    helper_text="Adapter registered locally; no UI descriptor has been added yet.",
                )
            descriptors.append(descriptor)
        return descriptors

    def list_brand_overviews(
        self, *, query: str | None = None, limit: int = 100
    ) -> list[IntelBrandOverview]:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.list_brand_overviews(conn, query=query, limit=limit)

    def list_resources(
        self,
        *,
        brand: str | None = None,
        source_id: str | None = None,
        include_backfill: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[IntelResourceView]:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.list_resources(
                conn,
                brand=brand,
                source_id=source_id,
                include_backfill=include_backfill,
                limit=limit,
                offset=offset,
            )

    def count_resources(
        self,
        *,
        brand: str | None = None,
        source_id: str | None = None,
        include_backfill: bool = True,
    ) -> int:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.count_resources(
                conn,
                brand=brand,
                source_id=source_id,
                include_backfill=include_backfill,
            )

    def get_resource(self, resource_id: str) -> IntelResourceView | None:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.get_resource(conn, resource_id)

    def resource_history(self, resource_id: str, *, limit: int = 50) -> list[dict]:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.list_resource_observations(conn, resource_id, limit=limit)

    def list_runs(self, *, limit: int = 50) -> list[dict]:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.list_runs(conn, limit=limit)

    def get_run(self, run_id: str) -> dict | None:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.get_run(conn, run_id)

    def run_crawl(
        self, *, due: bool = False, source_id: str | None = None, brand: str | None = None
    ) -> CrawlRunSummary:
        return IntelRunner(self.config, repo=self.repo).run(
            due=due, source_id=source_id, brand=brand
        )

    def queue_crawl(
        self, *, due: bool = False, source_id: str | None = None, brand: str | None = None
    ) -> CrawlRunSummary:
        run_id = new_run_id()
        with self.repo.connect() as conn:
            self.repo.queue_run(
                conn,
                run_id,
                {"due": due, "source_id": source_id, "brand": brand},
            )
            conn.commit()
        return CrawlRunSummary(run_id=run_id, status="queued")

    def run_queued_crawl(
        self,
        run_id: str,
        *,
        due: bool = False,
        source_id: str | None = None,
        brand: str | None = None,
    ) -> None:
        try:
            IntelRunner(self.config, repo=self.repo).run(
                due=due, source_id=source_id, brand=brand, run_id=run_id
            )
        except Exception as exc:
            logger.error(
                "intel_queued_run_failed",
                run_id=run_id,
                stage="crawl",
                traceback=safe_traceback(exc),
            )
            with self.repo.connect() as conn:
                self.repo.finish_run(
                    conn,
                    run_id,
                    status="failed",
                    source_count=0,
                    resource_count=0,
                    signal_count=0,
                    summary={"items": []},
                    error="Crawler setup failed; inspect structured logs.",
                )
                conn.commit()

    def resource_screenshot_path(self, resource_id: str) -> Path | None:
        """Locate a resource's card-screenshot file for serving over the API.

        Returns ``None`` unless the stored path resolves to an existing file inside the
        crawler's own cache directory — screenshots are the only local files a resource
        may reference, and the cache root confines what the endpoint can expose.
        """
        with self.repo.connect(readonly=True) as conn:
            metadata = self.repo.get_resource_metadata(conn, resource_id)
        if metadata is None:
            return None
        raw = str(metadata.get("screenshot_path") or "").strip()
        if not raw:
            return None
        path = Path(raw).expanduser().resolve()
        cache_root = self.config.cache_dir.expanduser().resolve()
        if not path.is_file() or not path.is_relative_to(cache_root):
            return None
        return path

    # ---- source registry (DB is the source of truth; the UI/CLI curate it) -------

    def list_sources(
        self, *, enabled_only: bool = False, brand: str | None = None
    ) -> list[IntelSource]:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.list_sources(conn, enabled_only=enabled_only, brand=brand)

    def get_source(self, source_id: str) -> IntelSource | None:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.get_source(conn, source_id)

    def get_source_status(self, source_id: str, *, run_limit: int = 20) -> IntelSourceStatus | None:
        with self.repo.connect(readonly=True) as conn:
            source = self.repo.get_source(conn, source_id)
            if source is None:
                return None
            state = self.repo.get_source_state(conn, source_id)
            recent_runs = self.repo.list_source_runs(conn, source_id, limit=run_limit)
        return IntelSourceStatus(source=source, state=state, recent_runs=recent_runs)

    def list_source_statuses(self, *, brand: str | None = None) -> list[IntelSourceStatus]:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.list_source_statuses(conn, brand=brand)

    def default_tier(self, source_type: str) -> Tier:
        return canonical_tier(source_type)

    def upsert_source(self, source: IntelSource) -> IntelSource:
        """Create or update a source. Preserves any existing `source_activated_at`."""
        source = source.model_copy(update={"tier": canonical_tier(source.source_type, source.tier)})
        with self.repo.connect() as conn:
            self.repo.sync_sources(conn, [source])
            conn.commit()
            stored = self.repo.get_source(conn, source.id)
        if stored is None:  # pragma: no cover - just written
            raise KeyError(source.id)
        return stored

    def set_source_enabled(self, source_id: str, enabled: bool) -> IntelSource | None:
        with self.repo.connect() as conn:
            self.repo.set_source_enabled(conn, source_id, enabled)
            conn.commit()
            return self.repo.get_source(conn, source_id)

    def delete_source(self, source_id: str) -> bool:
        with self.repo.connect() as conn:
            deleted = self.repo.delete_source(conn, source_id)
            conn.commit()
            return deleted

    def resolve_source(self, source_id: str) -> IntelSource | None:
        """Resolve a source's brand → platform id and persist it. Returns the updated source.

        Returns ``None`` if the source is unknown, its type has no resolver, or no confident
        match was found (refuse-to-guess — never sets a dealer/look-alike id). Legal-name hints
        come from ``source.config["resolve_names"]`` (e.g. Ford → "Ford Motor Company").
        """
        source = self.get_source(source_id)
        if source is None:
            return None
        accept = tuple(str(n) for n in (source.config.get("resolve_names") or []))
        resolved_id = self._resolve_platform_id(source.source_type, source.brand_name, accept)
        if not resolved_id:
            return None
        return self.upsert_source(source.model_copy(update={"platform_id": resolved_id}))

    @staticmethod
    def _resolve_platform_id(
        source_type: str, brand: str, accept_names: tuple[str, ...]
    ) -> str | None:
        if source_type == "google_atc":
            from ad_classifier.intelligence_crawler.google_atc_rpc import (
                default_rpc_fetch,
                resolve_advertiser,
            )

            match = resolve_advertiser(
                brand,
                fetch=default_rpc_fetch,
                accept_names=accept_names,
                extra_queries=accept_names,
            )
            return match["advertiser_id"] if match else None
        if source_type == "meta_ad_library_ui":
            from ad_classifier.intelligence_crawler.meta_ad_library_probe import (
                meta_page_search,
                resolve_meta_page,
            )

            match = resolve_meta_page(brand, search=meta_page_search, accept_names=accept_names)
            return match["page_id"] if match else None
        return None
