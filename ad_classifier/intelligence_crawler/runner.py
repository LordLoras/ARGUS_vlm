"""Crawl orchestration with atomic current-state and append-only observation writes."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

import structlog

from ad_classifier.intelligence_crawler import dedup, detect, scoring
from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.contract import resource_snapshot, snapshot_hash
from ad_classifier.intelligence_crawler.diagnostics import (
    classify_exception,
    safe_traceback,
)
from ad_classifier.intelligence_crawler.ids import (
    change_id,
    evidence_id,
    new_run_id,
    observation_id,
    signal_id,
)
from ad_classifier.intelligence_crawler.models import (
    CrawlRunSummary,
    IntelEvidence,
    IntelResource,
    IntelResourceObservation,
    IntelSignal,
    IntelSource,
    SourcePollResult,
    SourceRunItem,
)
from ad_classifier.intelligence_crawler.repository import IntelRepository
from ad_classifier.intelligence_crawler.request_guard import request_guard
from ad_classifier.intelligence_crawler.run_policy import (
    media_assets,
    normalize_poll_result,
    overall_status,
    poll_reason,
    primary_diagnostic,
    schedule,
)
from ad_classifier.intelligence_crawler.sources import base as source_base
from ad_classifier.intelligence_crawler.timeutils import as_utc, utcnow

logger = structlog.get_logger(__name__)

# UI-driven providers can take minutes to scroll and enrich. A run-specific owner plus an
# atomic compare-and-set lease prevents two workers from polling the same source.
LEASE_TTL_SECONDS = 3_600
AdapterFactory = Callable[[str], source_base.SourceAdapter]


class IntelRunner:
    def __init__(
        self,
        config: IntelConfig,
        *,
        repo: IntelRepository | None = None,
        adapter_factory: AdapterFactory | None = None,
        now_fn: Callable[[], datetime] | None = None,
        owner: str | None = None,
    ) -> None:
        self.config = config
        self.repo = repo or IntelRepository(config.db_path)
        self.adapter_factory = adapter_factory or self._default_adapter_factory
        self.now_fn = now_fn or utcnow
        self.owner = owner or f"intel-runner-{uuid4().hex[:12]}"

    def _default_adapter_factory(self, source_type: str) -> source_base.SourceAdapter:
        return source_base.build_adapter(source_type, intel_config=self.config)

    def run(
        self,
        *,
        due: bool = False,
        source_id: str | None = None,
        brand: str | None = None,
        run_id: str | None = None,
        force: bool = False,
    ) -> CrawlRunSummary:
        reserved_run_id = run_id
        run_id = reserved_run_id or new_run_id()
        items: list[SourceRunItem] = []

        with self.repo.connect() as conn:
            if reserved_run_id:
                self.repo.start_run(conn, run_id)
            else:
                self.repo.create_run(conn, run_id)
            self.repo.seed_sources(conn, [source.to_source() for source in self.config.sources])
            conn.commit()
            selected = self._select_sources(
                conn, due=due, source_id=source_id, brand=brand, now=self._now()
            )

            for source in selected:
                try:
                    item = self._process_source(
                        conn,
                        run_id,
                        source,
                        force=force,
                        respect_freshness=source_id is not None,
                    )
                    conn.commit()
                except Exception as exc:  # isolate one provider/source from the rest
                    conn.rollback()
                    logger.error(
                        "intel_source_failed",
                        source_id=source.id,
                        stage="crawl",
                        run_id=run_id,
                        traceback=safe_traceback(exc),
                    )
                    item = self._record_source_error(conn, run_id, source, exc)
                items.append(item)

            status = overall_status(items)
            total_resources = sum(item.new_resources for item in items)
            total_signals = sum(item.new_signals for item in items)
            self.repo.finish_run(
                conn,
                run_id,
                status=status,
                source_count=len(selected),
                resource_count=total_resources,
                signal_count=total_signals,
                summary={"items": [item.model_dump(mode="json") for item in items]},
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
        self,
        conn: sqlite3.Connection,
        run_id: str,
        source_ref: IntelSource,
        *,
        force: bool,
        respect_freshness: bool,
    ) -> SourceRunItem:
        now = self._now()
        if not force:
            guard = request_guard(
                self.repo,
                conn,
                source_ref,
                now,
                respect_freshness=respect_freshness,
            )
            if guard is not None:
                log = logger.warning if guard.failure_category else logger.info
                log(
                    "intel_source_request_guarded",
                    source_id=source_ref.id,
                    source_type=source_ref.source_type,
                    stage="request_guard",
                    stop_reason=guard.stop_reason,
                    error_code=guard.error_code,
                    next_due_at=guard.next_due_at,
                )
                self._store_skipped_run(conn, run_id, source_ref.id, now, guard)
                return guard
        lease_owner = self._lease_owner(run_id, source_ref.id)
        if not self.repo.acquire_lease(
            conn, source_ref.id, lease_owner, now=now, ttl_seconds=LEASE_TTL_SECONDS
        ):
            item = SourceRunItem(
                source_id=source_ref.id,
                status="skipped",
                complete=False,
                reason="Source is currently leased by another crawl run.",
            )
            self._store_skipped_run(conn, run_id, source_ref.id, now, item)
            return item

        self.repo.start_source_run(conn, run_id, source_ref.id, started_at=now)
        conn.commit()  # durable running ledger before the network/browser operation
        try:
            source = self.repo.get_source(conn, source_ref.id)
            if source is None:
                item = SourceRunItem(
                    source_id=source_ref.id,
                    status="skipped",
                    complete=False,
                    reason="Source was archived before polling began.",
                )
                self._finish_source_run(conn, run_id, item)
                return item

            state = self.repo.get_source_state(conn, source.id)
            if source.source_type == "google_atc":
                state = state.model_copy(
                    update={
                        "runtime_context": {
                            "resource_index": self.repo.resource_metadata_index(conn, source.id)
                        }
                    }
                )
            self.repo.update_source_state(conn, source.id, last_attempt_at=now)
            conn.commit()

            adapter = self.adapter_factory(source.source_type)
            checkpoint_setter = getattr(adapter, "set_checkpoint_sink", None)
            if callable(checkpoint_setter):

                def persist_provider_state(provider_state: dict) -> None:
                    self.repo.update_source_state(conn, source.id, state_json=provider_state)
                    conn.commit()

                checkpoint_setter(persist_provider_state)
            result = adapter.poll(source, state, now=now)
            result = normalize_poll_result(result, source.source_type)
            self.repo.renew_lease(
                conn,
                source.id,
                lease_owner,
                now=self._now(),
                ttl_seconds=LEASE_TTL_SECONDS,
            )
            if self.repo.get_source(conn, source.id) is None:
                item = SourceRunItem(
                    source_id=source.id,
                    status="skipped",
                    complete=False,
                    reason="Source was archived during polling; provider result was discarded.",
                )
                self._finish_source_run(conn, run_id, item, result=result)
                return item
            if result.outcome == "failed":
                return self._record_poll_failure(conn, run_id, source, state, result, now)

            detection = detect.classify(
                source=source,
                items=result.items,
                seen_ids=self.repo.existing_resource_ids(conn, source.id),
                now=now,
                lookback_days=self.config.detection.new_signal_lookback_days,
                activated_at=source.source_activated_at,
            )
            if result.verified_external_ids:
                self.repo.touch_resources_seen(
                    conn,
                    source.id,
                    result.verified_external_ids,
                    seen_at=now,
                )
            counts = self._persist_detection(conn, run_id, source, detection, now)

            # An incomplete baseline must not activate the source: the next complete poll is
            # still baseline, preventing a partial catalog from emitting false "new" signals.
            if detection.baseline_mode and result.complete:
                self.repo.set_source_activated(conn, source.id, detection.activated_at)

            consecutive = state.consecutive_errors + (0 if result.complete else 1)
            next_due, cooldown = schedule(source, now, result, consecutive)
            primary = primary_diagnostic(result.diagnostics)
            self.repo.update_source_state(
                conn,
                source.id,
                last_success_at=now if result.complete else state.last_success_at,
                last_error=primary.message if primary else None,
                consecutive_errors=0 if result.complete else consecutive,
                next_due_at=next_due,
                cooldown_until=cooldown,
                last_outcome=result.outcome,
                last_error_category=primary.category if primary else None,
                last_error_code=primary.code if primary else None,
                diagnostics_json=result.diagnostics,
                watermark=(result.new_watermark or state.watermark),
                etag=(result.etag or state.etag),
                last_modified=(result.last_modified or state.last_modified),
                state_json=(
                    result.state_updates
                    if result.state_updates is not None
                    else state.provider_state
                ),
            )
            status = "polled" if result.complete else "partial"
            reason = poll_reason(result, detection.baseline_mode)
            item = SourceRunItem(
                source_id=source.id,
                status=status,
                baseline=detection.baseline_mode,
                reason=reason,
                outcome=result.outcome,
                complete=result.complete,
                truncated=result.truncated,
                truncation_reason=result.truncation_reason,
                failure_category=primary.category if primary else None,
                error_code=primary.code if primary else None,
                diagnostics=result.diagnostics,
                next_due_at=next_due,
                scan_mode=result.scan_mode,
                resumed=result.resumed,
                checkpoint_page=result.checkpoint_page,
                stop_reason=result.stop_reason,
                **counts,
            )
            self._finish_source_run(conn, run_id, item, result=result)
            return item
        finally:
            self.repo.release_lease(conn, source_ref.id, lease_owner)

    def _persist_detection(self, conn, run_id, source, detection, now) -> dict[str, int]:
        counts = {
            "new_resources": 0,
            "new_signals": 0,
            "backfilled": 0,
            "filtered": 0,
            "refreshed": 0,
        }
        for decision in detection.decisions:
            if self._persist_resource(conn, decision, source, run_id, now):
                counts["new_resources"] += 1
            if decision.kind == "backfill":
                counts["backfilled"] += 1
            elif not scoring.is_ad_signal_candidate(decision.item, self.config.scoring):
                counts["filtered"] += 1
            elif self._emit_signal(conn, source, decision, now):
                counts["new_signals"] += 1
        for refresh in detection.refreshes:
            self._persist_resource(conn, refresh, source, run_id, now)
            counts["refreshed"] += 1
        return counts

    def _persist_resource(self, conn, decision, source, run_id, now) -> bool:
        resource = self._build_resource(decision, source, run_id, now)
        previous_hash = self.repo.get_resource_snapshot_hash(conn, resource.id)
        current_snapshot = resource_snapshot(resource)
        current_hash = snapshot_hash(current_snapshot)
        inserted = self.repo.insert_resource(conn, resource)
        snapshot = resource.model_dump(mode="json", exclude={"metadata"})
        self.repo.insert_observation(
            conn,
            IntelResourceObservation(
                id=observation_id(run_id, resource.id),
                resource_id=resource.id,
                source_id=source.id,
                run_id=run_id,
                observed_at=now,
                payload_hash=current_hash,
                resource=snapshot,
                metadata=resource.metadata,
            ),
        )
        if inserted or previous_hash != current_hash:
            self.repo.insert_resource_change(
                conn,
                change_id=change_id(run_id, resource.id),
                resource_id=resource.id,
                source_id=source.id,
                run_id=run_id,
                change_type="created" if inserted else "updated",
                changed_at=now,
                content_hash=current_hash,
                previous_content_hash=previous_hash,
            )
        for asset in media_assets(resource):
            self.repo.upsert_media_asset(conn, asset)
        return inserted

    def _build_resource(self, decision, source: IntelSource, run_id: str, now: datetime):
        item = decision.item
        raw_variant = item.raw.get("creative_variant_count")
        variant_count = raw_variant if isinstance(raw_variant, int) else None
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
            last_seen_at=now,
            fetched_at=now,
            is_backfill=decision.kind == "backfill",
            variant_count=variant_count,
            has_variants=bool(item.raw.get("has_multiple_versions"))
            or bool(variant_count and variant_count > 1),
            thumbnail_url=item.thumbnail_url,
            duration_ms=item.duration_ms,
            metadata=item.raw,
        )

    def _record_poll_failure(self, conn, run_id, source, state, result, now):
        primary = primary_diagnostic(result.diagnostics)
        consecutive = state.consecutive_errors + 1
        next_due, cooldown = schedule(source, now, result, consecutive)
        self.repo.update_source_state(
            conn,
            source.id,
            last_error=primary.message if primary else "Provider poll failed.",
            consecutive_errors=consecutive,
            next_due_at=next_due,
            cooldown_until=cooldown,
            last_outcome="failed",
            last_error_category=primary.category if primary else "unknown",
            last_error_code=primary.code if primary else "provider_poll_failed",
            diagnostics_json=result.diagnostics,
            state_json=(
                result.state_updates if result.state_updates is not None else state.provider_state
            ),
        )
        item = SourceRunItem(
            source_id=source.id,
            status="failed",
            outcome="failed",
            complete=False,
            reason=primary.message if primary else "Provider poll failed.",
            failure_category=primary.category if primary else "unknown",
            error_code=primary.code if primary else "provider_poll_failed",
            diagnostics=result.diagnostics,
            next_due_at=next_due,
            scan_mode=result.scan_mode,
            resumed=result.resumed,
            checkpoint_page=result.checkpoint_page,
            stop_reason=result.stop_reason,
        )
        self._finish_source_run(conn, run_id, item, result=result)
        return item

    def _record_source_error(self, conn, run_id, source, exc: Exception) -> SourceRunItem:
        diagnostic = classify_exception(exc, provider=source.source_type, phase="poll")
        now = self._now()
        state = self.repo.get_source_state(conn, source.id)
        result = SourcePollResult(
            source_id=source.id,
            outcome="failed",
            complete=False,
            diagnostics=[diagnostic],
        )
        # The durable source-run row normally exists; create it if setup failed before it did.
        exists = conn.execute(
            "SELECT 1 FROM intel_source_runs WHERE run_id=? AND source_id=?",
            (run_id, source.id),
        ).fetchone()
        if exists is None:
            self.repo.start_source_run(conn, run_id, source.id, started_at=now)
        item = self._record_poll_failure(conn, run_id, source, state, result, now)
        self.repo.release_lease(conn, source.id, self._lease_owner(run_id, source.id))
        conn.commit()
        return item

    def _store_skipped_run(self, conn, run_id, source_id, now, item) -> None:
        self.repo.start_source_run(conn, run_id, source_id, started_at=now)
        self._finish_source_run(conn, run_id, item)

    def _finish_source_run(self, conn, run_id, item, result=None) -> None:
        self.repo.finish_source_run(
            conn,
            run_id,
            item.source_id,
            status=item.status,
            outcome=item.outcome,
            complete=item.complete,
            truncated=item.truncated,
            truncation_reason=item.truncation_reason,
            new_resources=item.new_resources,
            refreshed=item.refreshed,
            backfilled=item.backfilled,
            filtered=item.filtered,
            new_signals=item.new_signals,
            error_category=item.failure_category,
            error_code=item.error_code,
            error=item.reason if item.status == "failed" else None,
            diagnostics=item.diagnostics,
            request_count=result.request_count if result else 0,
            page_count=result.page_count if result else 0,
            provider_item_count=result.provider_item_count if result else None,
            next_due_at=item.next_due_at,
            scan_mode=item.scan_mode,
            resumed=item.resumed,
            checkpoint_page=item.checkpoint_page,
            stop_reason=item.stop_reason,
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
            evidence=[
                IntelEvidence(
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
            ],
        )
        return self.repo.insert_signal(conn, signal)

    def _select_sources(self, conn, *, due, source_id, brand, now) -> list[IntelSource]:
        if source_id:
            source = self.repo.get_source(conn, source_id)
            return [source] if source is not None else []
        return self.repo.list_sources(
            conn, enabled_only=True, brand=brand, due_at=now if due else None
        )

    def _lease_owner(self, run_id: str, source_id: str) -> str:
        return f"{self.owner}:{run_id}:{source_id}"

    def _now(self) -> datetime:
        now = as_utc(self.now_fn())
        assert now is not None
        return now
