"""Orchestrates a crawl: select sources → lease → poll → detect → group → score → persist.

Depends only on the :class:`SourceAdapter` interface (via ``adapter_factory``), so new
source integrations require no change here. Per-source failures are isolated: one source
raising marks the run ``degraded`` and the others still persist.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime

import structlog

from ad_classifier.entity_graph.utils import normalize_name
from ad_classifier.intelligence_crawler import dedup, detect, scoring
from ad_classifier.intelligence_crawler.config import IntelConfig, SourceConfig
from ad_classifier.intelligence_crawler.ids import evidence_id, new_run_id, signal_id
from ad_classifier.intelligence_crawler.models import (
    CrawlRunSummary,
    IntelEvidence,
    IntelResource,
    IntelSignal,
    IntelSource,
    RunStatus,
    SourceRunItem,
)
from ad_classifier.intelligence_crawler.repository import IntelRepository
from ad_classifier.intelligence_crawler.sources import base as source_base
from ad_classifier.intelligence_crawler.timeutils import as_utc, utcnow

logger = structlog.get_logger(__name__)

LEASE_TTL_SECONDS = 600

AdapterFactory = Callable[[str], source_base.SourceAdapter]


class IntelRunner:
    def __init__(
        self,
        config: IntelConfig,
        *,
        repo: IntelRepository | None = None,
        adapter_factory: AdapterFactory | None = None,
        now_fn: Callable[[], datetime] | None = None,
        owner: str = "intel-runner",
    ) -> None:
        self.config = config
        self.repo = repo or IntelRepository(config.db_path)
        self.adapter_factory = adapter_factory or self._default_adapter_factory
        self.now_fn = now_fn or utcnow
        self.owner = owner

    def _default_adapter_factory(self, source_type: str) -> source_base.SourceAdapter:
        return source_base.build_adapter(source_type, intel_config=self.config)

    def run(
        self, *, due: bool = False, source_id: str | None = None, brand: str | None = None
    ) -> CrawlRunSummary:
        run_id = new_run_id()
        selected = self._select_sources(due=due, source_id=source_id, brand=brand)
        items: list[SourceRunItem] = []
        total_resources = 0
        total_signals = 0
        degraded = False

        with self.repo.connect() as conn:
            self.repo.create_run(conn, run_id)
            self.repo.sync_sources(conn, [s.to_source() for s in self.config.sources])
            conn.commit()

            for source_cfg in selected:
                try:
                    item = self._process_source(conn, run_id, source_cfg)
                    conn.commit()
                except Exception as exc:  # whole-source failure: isolate and continue
                    conn.rollback()
                    degraded = True
                    logger.error("intel_source_failed", source_id=source_cfg.id, error=str(exc))
                    self._record_source_error(conn, source_cfg.id, exc)
                    item = SourceRunItem(
                        source_id=source_cfg.id, status="failed", reason=str(exc)[:240]
                    )
                items.append(item)
                total_resources += item.new_resources
                total_signals += item.new_signals
                if item.status == "failed":
                    degraded = True

            status: RunStatus = "degraded" if degraded else "completed"
            self.repo.finish_run(
                conn,
                run_id,
                status=status,
                source_count=len(selected),
                resource_count=total_resources,
                signal_count=total_signals,
                summary={"items": [i.model_dump() for i in items]},
            )
            conn.commit()

        return CrawlRunSummary(
            run_id=run_id,
            status=status,
            source_count=len(selected),
            resource_count=total_resources,
            signal_count=total_signals,
            items=items,
        )

    def _process_source(
        self, conn: sqlite3.Connection, run_id: str, source_cfg: SourceConfig
    ) -> SourceRunItem:
        now = as_utc(self.now_fn())
        assert now is not None
        if not self.repo.acquire_lease(
            conn, source_cfg.id, self.owner, now=now, ttl_seconds=LEASE_TTL_SECONDS
        ):
            return SourceRunItem(
                source_id=source_cfg.id, status="skipped", reason="locked by another run"
            )
        try:
            source = self.repo.get_source(conn, source_cfg.id)
            if source is None:  # pragma: no cover - synced just above
                return SourceRunItem(source_id=source_cfg.id, status="skipped", reason="not synced")
            state = self.repo.get_source_state(conn, source.id)
            adapter = self.adapter_factory(source.source_type)
            self.repo.update_source_state(conn, source.id, last_attempt_at=now)

            result = adapter.poll(source, state, now=now)
            seen_ids = self.repo.existing_resource_ids(conn, source.id)
            detection = detect.classify(
                source=source,
                items=result.items,
                seen_ids=seen_ids,
                now=now,
                lookback_days=self.config.detection.new_signal_lookback_days,
                activated_at=source.source_activated_at,
            )

            new_resources = 0
            new_signals = 0
            backfilled = 0
            for decision in detection.decisions:
                if self.repo.insert_resource(
                    conn, self._build_resource(decision, source, run_id, now)
                ):
                    new_resources += 1
                if decision.kind == "backfill":
                    backfilled += 1
                    continue
                if self._emit_signal(conn, source, decision, now):
                    new_signals += 1

            if detection.baseline_mode:
                self.repo.set_source_activated(conn, source.id, detection.activated_at)
            self.repo.update_source_state(
                conn,
                source.id,
                last_success_at=now,
                last_error=None,
                consecutive_errors=0,
                watermark=result.new_watermark or state.watermark,
                etag=result.etag or state.etag,
                last_modified=result.last_modified or state.last_modified,
            )
            return SourceRunItem(
                source_id=source.id,
                status="polled",
                new_resources=new_resources,
                new_signals=new_signals,
                backfilled=backfilled,
                baseline=detection.baseline_mode,
                reason="baseline first poll (no live signals)" if detection.baseline_mode else None,
            )
        finally:
            self.repo.release_lease(conn, source_cfg.id)

    def _build_resource(
        self, decision, source: IntelSource, run_id: str, now: datetime
    ) -> IntelResource:
        item = decision.item
        return IntelResource(
            id=decision.resource_id,
            source_id=source.id,
            run_id=run_id,
            resource_type=item.resource_type,
            url=item.url,
            canonical_url=item.canonical_url,
            platform=source.platform,
            platform_id=item.external_id,
            title=item.title,
            description=item.description,
            published_at=item.published_at,
            first_seen_at=now,
            fetched_at=now,
            is_backfill=(decision.kind == "backfill"),
            metadata=item.raw,
        )

    def _emit_signal(self, conn, source: IntelSource, decision, now: datetime) -> bool:
        item = decision.item
        group_key = dedup.campaign_group_key(source.brand_name, item, fallback=now)
        group_id = self.repo.get_or_create_campaign_group(
            conn,
            brand_name=source.brand_name,
            group_key=group_key,
            title=dedup.campaign_title(item),
            now=now,
        )
        corroborating = self.repo.group_signal_count(conn, group_id)
        confidence, status, breakdown = scoring.score_signal(
            tier=source.tier,
            item=item,
            corroborating_count=corroborating,
            config=self.config.scoring,
        )
        signal_type = scoring.classify_signal_type(item)
        sid = signal_id(source.id, item.external_id, signal_type)
        evidence = IntelEvidence(
            id=evidence_id(sid, decision.resource_id),
            signal_id=sid,
            resource_id=decision.resource_id,
            source_id=source.id,
            evidence_type=item.resource_type,
            url=item.url,
            text=item.title,
            published_at=item.published_at,
            confidence=confidence,
        )
        signal = IntelSignal(
            id=sid,
            brand_name=source.brand_name,
            campaign_group_id=group_id,
            signal_type=signal_type,
            status=status,
            confidence=confidence,
            title=item.title or f"{source.brand_name}: new {signal_type}",
            summary=item.description,
            campaign_name=dedup.campaign_title(item),
            first_seen_at=now,
            source_published_at=item.published_at,
            last_seen_at=now,
            score_breakdown=breakdown,
            evidence=[evidence],
        )
        return self.repo.insert_signal(conn, signal)

    def _record_source_error(
        self, conn: sqlite3.Connection, source_id: str, exc: Exception
    ) -> None:
        try:
            self.repo.release_lease(conn, source_id)
            self.repo.update_source_state(conn, source_id, last_error=str(exc)[:240])
            conn.commit()
        except sqlite3.Error:  # pragma: no cover - best effort
            logger.warning("intel_error_record_failed", source_id=source_id)

    def _select_sources(
        self, *, due: bool, source_id: str | None, brand: str | None
    ) -> list[SourceConfig]:
        if source_id:  # explicit single source: run even if disabled
            return [s for s in self.config.sources if s.id == source_id]
        selected = self.config.enabled_sources()
        if brand:
            key = normalize_name(brand)
            selected = [s for s in selected if normalize_name(s.brand) == key]
        # NOTE: --due currently means "all enabled". Per-source next_due_at filtering using
        # intel_source_state is a planned refinement (runbook §32.5 scheduling).
        return selected
