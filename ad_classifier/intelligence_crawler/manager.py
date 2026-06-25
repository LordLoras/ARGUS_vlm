"""Facade over the intelligence crawler for API/CLI callers (mirrors EntityGraphManager).

Holds the config + a single repository, and exposes read methods (read-only connection)
plus a crawl trigger. Keeps routers thin and the DB wiring in one place.
"""

from __future__ import annotations

from datetime import datetime

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.digest import build_digest
from ad_classifier.intelligence_crawler.models import (
    CrawlRunSummary,
    DigestEntry,
    IntelSignal,
    IntelSource,
    WatchedBrand,
)
from ad_classifier.intelligence_crawler.repository import IntelRepository
from ad_classifier.intelligence_crawler.runner import IntelRunner
from ad_classifier.intelligence_crawler.sources.base import available_source_types
from ad_classifier.intelligence_crawler.watchlist import build_watchlist


class IntelManager:
    def __init__(self, config: IntelConfig, *, repo: IntelRepository | None = None) -> None:
        self.config = config
        self.repo = repo or IntelRepository(config.db_path)

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

    def run_crawl(
        self, *, due: bool = False, source_id: str | None = None, brand: str | None = None
    ) -> CrawlRunSummary:
        return IntelRunner(self.config, repo=self.repo).run(
            due=due, source_id=source_id, brand=brand
        )

    # ---- source registry (DB is the source of truth; the UI/CLI curate it) -------

    def list_sources(
        self, *, enabled_only: bool = False, brand: str | None = None
    ) -> list[IntelSource]:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.list_sources(conn, enabled_only=enabled_only, brand=brand)

    def get_source(self, source_id: str) -> IntelSource | None:
        with self.repo.connect(readonly=True) as conn:
            return self.repo.get_source(conn, source_id)

    def upsert_source(self, source: IntelSource) -> IntelSource:
        """Create or update a source. Preserves any existing `source_activated_at`."""
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
