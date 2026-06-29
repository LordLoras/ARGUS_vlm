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

from ad_classifier.intelligence_crawler import dedup, detect, scoring
from ad_classifier.intelligence_crawler.config import IntelConfig
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
        items: list[SourceRunItem] = []
        total_resources = 0
        total_signals = 0
        degraded = False

        with self.repo.connect() as conn:
            self.repo.create_run(conn, run_id)
            # YAML sources are a seed: upsert them, then select from the DB — the source of
            # truth, which also holds sources added via the API/UI. (`due` is accepted for
            # API/CLI compatibility; today it means "all enabled".)
            self.repo.sync_sources(conn, [s.to_source() for s in self.config.sources])
            conn.commit()
            selected = self._select_sources(conn, source_id=source_id, brand=brand)

            for source_ref in selected:
                try:
                    item = self._process_source(conn, run_id, source_ref)
                    conn.commit()
                except Exception as exc:  # whole-source failure: isolate and continue
                    conn.rollback()
                    degraded = True
                    logger.error("intel_source_failed", source_id=source_ref.id, error=str(exc))
                    self._record_source_error(conn, source_ref.id, exc)
                    item = SourceRunItem(
                        source_id=source_ref.id, status="failed", reason=str(exc)[:240]
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
        self, conn: sqlite3.Connection, run_id: str, source_ref: IntelSource
    ) -> SourceRunItem:
        now = as_utc(self.now_fn())
        assert now is not None
        if not self.repo.acquire_lease(
            conn, source_ref.id, self.owner, now=now, ttl_seconds=LEASE_TTL_SECONDS
        ):
            return SourceRunItem(
                source_id=source_ref.id, status="skipped", reason="locked by another run"
            )
        try:
            source = self.repo.get_source(conn, source_ref.id)
            if source is None:  # pragma: no cover - synced just above
                return SourceRunItem(source_id=source_ref.id, status="skipped", reason="not synced")
            state = self.repo.get_source_state(conn, source.id)
            adapter = self.adapter_factory(source.source_type)
            self.repo.update_source_state(conn, source.id, last_attempt_at=now)
            conn.commit()

            result = adapter.poll(source, state, now=now)
            if self.repo.get_source(conn, source.id) is None:
                return SourceRunItem(
                    source_id=source.id,
                    status="skipped",
                    reason="source deleted during poll",
                )
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
            filtered = 0
            for decision in detection.decisions:
                if self.repo.insert_resource(
                    conn, self._build_resource(decision, source, run_id, now)
                ):
                    new_resources += 1
                if decision.kind == "backfill":
                    backfilled += 1
                    continue
                # Ad-likelihood gate: a non-ad-like video (walkaround, interview, how-to) is
                # recorded as a resource but does not emit a `new_ad_upload` signal.
                if not scoring.is_ad_signal_candidate(decision.item, self.config.scoring):
                    filtered += 1
                    continue
                if self._emit_signal(conn, source, decision, now):
                    new_signals += 1

            if detection.baseline_mode:
                self.repo.set_source_activated(conn, source.id, detection.activated_at)
            # A poll that returned errors (e.g. HTTP 4xx, bad config) but didn't raise is
            # "degraded evidence": surface it on the source state and the run item, but keep
            # going — it is not a whole-source failure.
            poll_error = "; ".join(result.errors)[:240] if result.errors else None
            self.repo.update_source_state(
                conn,
                source.id,
                last_success_at=now,
                last_error=poll_error,
                consecutive_errors=0,
                watermark=result.new_watermark or state.watermark,
                etag=result.etag or state.etag,
                last_modified=result.last_modified or state.last_modified,
            )
            if detection.baseline_mode:
                reason = "baseline first poll (no live signals)"
            elif poll_error:
                reason = f"poll errors: {poll_error}"
            else:
                reason = None
            return SourceRunItem(
                source_id=source.id,
                status="polled",
                new_resources=new_resources,
                new_signals=new_signals,
                backfilled=backfilled,
                filtered=filtered,
                baseline=detection.baseline_mode,
                reason=reason,
            )
        finally:
            self.repo.release_lease(conn, source_ref.id)

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
        self, conn: sqlite3.Connection, *, source_id: str | None, brand: str | None
    ) -> list[IntelSource]:
        """Select crawl targets from the DB registry (source of truth)."""
        if source_id:  # explicit single source: run even if disabled
            source = self.repo.get_source(conn, source_id)
            return [source] if source is not None else []
        # Per-source next_due_at filtering is a planned refinement (runbook §32.5).
        return self.repo.list_sources(conn, enabled_only=True, brand=brand)
