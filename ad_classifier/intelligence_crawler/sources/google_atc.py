"""Google Ads Transparency Center source adapter — brand/advertiser-anchored, US-only.

Mirrors the Meta adapter's shape: anchor on a stable advertiser id (``platform_id`` =
ATC ``AR…`` id), list that advertiser's US creatives, and convert them to
``RawSourceItem`` records. Data comes from ATC's internal RPC (see
``google_atc_rpc`` — an opt-in exception to the no-hidden-endpoint guideline).

The RPC transport is injected (``rpc_fetch``) so the adapter is fully testable offline.
Following the YouTube adapter's posture, when a feed/``http`` client is injected (tests)
the RPC client defaults to **disabled** unless one is injected too — so a unit test never
makes a live call.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from urllib.error import HTTPError

import structlog

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.diagnostics import (
    classify_exception,
    configuration_diagnostic,
    safe_traceback,
)
from ad_classifier.intelligence_crawler.google_atc_rpc import (
    US_REGION_CODE,
    PreviewFetch,
    RpcFetch,
    default_preview_fetch,
    default_rpc_fetch,
    search_creatives_result,
)
from ad_classifier.intelligence_crawler.google_crawl_state import (
    after_success,
    checkpoint_summary,
    clear_checkpoint,
    is_known_unchanged,
    plan_scan,
    preview_needs_refresh,
    with_checkpoint,
)
from ad_classifier.intelligence_crawler.google_creatives import (
    creative_to_item,
    enrich_preview_artifacts,
    latest_published,
)
from ad_classifier.intelligence_crawler.models import (
    IntelSource,
    PollDiagnostic,
    SourcePollResult,
    SourceState,
    Tier,
)
from ad_classifier.intelligence_crawler.sources.base import register_source

logger = structlog.get_logger(__name__)

GOOGLE_ATC_SOURCE_TYPE = "google_atc"
# Politeness pauses between consecutive live requests. An uncapped poll can make hundreds
# of RPC pages and preview fetches; an unthrottled burst earns an HTTP 429.
_RPC_PAGE_DELAY_S = 0.75
_PREVIEW_FETCH_DELAY_S = 0.4

Sleep = Callable[[float], None]
CheckpointSink = Callable[[dict], None]


@register_source(GOOGLE_ATC_SOURCE_TYPE)
class GoogleAtcAdapter:
    """List a US advertiser's creatives from the Ads Transparency Center."""

    tier: Tier = "B"

    def __init__(
        self,
        *,
        http=None,
        intel_config: IntelConfig | None = None,
        rpc_fetch: RpcFetch | None = None,
        preview_fetch: PreviewFetch | None = None,
        sleep: Sleep | None = None,
    ) -> None:
        self._config = intel_config or IntelConfig()
        if rpc_fetch is not None:
            self._fetch: RpcFetch | None = rpc_fetch
            self._preview_fetch = preview_fetch
            self._sleep: Sleep = sleep or (lambda _s: None)  # injected transport: no waiting
        elif http is None:
            self._fetch = default_rpc_fetch  # production default
            self._preview_fetch = preview_fetch or default_preview_fetch
            self._sleep = sleep or time.sleep
        else:
            self._fetch = None  # injected feed client → no implicit network
            self._preview_fetch = preview_fetch
            self._sleep = sleep or (lambda _s: None)
        self._checkpoint_sink: CheckpointSink | None = None

    def set_checkpoint_sink(self, sink: CheckpointSink | None) -> None:
        """Install the runner's durable per-page state writer."""
        self._checkpoint_sink = sink

    def poll(self, source: IntelSource, state: SourceState, *, now: datetime) -> SourcePollResult:
        advertiser_id = (source.platform_id or "").strip()
        if not advertiser_id:
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=[
                    configuration_diagnostic(
                        "google_advertiser_id_missing",
                        "Google Ads Transparency source needs an AR advertiser ID.",
                        provider=GOOGLE_ATC_SOURCE_TYPE,
                    )
                ],
            )
        if self._fetch is None:  # pragma: no cover - guarded construction
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=[
                    configuration_diagnostic(
                        "google_rpc_client_unavailable",
                        "Google Ads Transparency RPC client is unavailable.",
                        provider=GOOGLE_ATC_SOURCE_TYPE,
                    )
                ],
            )

        page_size = _int_config(source.config.get("page_size"), default=40, minimum=1, maximum=100)
        max_pages = _page_limit_config(source.config)
        preview_limit = _preview_limit(source)
        full_reconcile_hours = _int_config(
            source.config.get("full_reconcile_hours"), default=72, minimum=1, maximum=720
        )
        checkpoint_ttl_hours = _int_config(
            source.config.get("checkpoint_ttl_hours"), default=24, minimum=1, maximum=168
        )
        unchanged_pages = _int_config(
            source.config.get("unchanged_pages_before_stop"),
            default=3,
            minimum=1,
            maximum=20,
        )
        plan = plan_scan(
            state,
            advertiser_id=advertiser_id,
            region=US_REGION_CODE,
            page_size=page_size,
            now=now,
            full_reconcile_hours=full_reconcile_hours,
            checkpoint_ttl_hours=checkpoint_ttl_hours,
            stop_after_unchanged_pages=unchanged_pages,
        )
        effective_mode = plan.checkpoint_mode if plan.mode == "resume" else plan.mode
        effective_mode = effective_mode if effective_mode in {"full", "incremental"} else "full"
        provider_state = state.provider_state
        resume_present, _resume_page = checkpoint_summary(provider_state)
        if plan.mode != "resume" and resume_present:
            provider_state = clear_checkpoint(provider_state)
            if self._checkpoint_sink is not None:
                self._checkpoint_sink(provider_state)
        checkpoint_offset = plan.prior_page_count

        def persist_checkpoint(token: str, page_count: int, _request_count: int) -> None:
            nonlocal provider_state
            provider_state = with_checkpoint(
                provider_state,
                token=token,
                fingerprint=plan.fingerprint,
                mode=effective_mode,
                page_count=checkpoint_offset + page_count,
                now=now,
            )
            if self._checkpoint_sink is not None:
                self._checkpoint_sink(provider_state)

        known_predicate = None
        stop_after_unchanged = 0
        if effective_mode == "incremental":

            def known_predicate(creative: dict) -> bool:
                return is_known_unchanged(creative, plan.known_index)

            stop_after_unchanged = plan.stop_after_unchanged_pages
        try:
            search = search_creatives_result(
                advertiser_id,
                fetch=_throttled(self._fetch, _RPC_PAGE_DELAY_S, self._sleep),
                region=US_REGION_CODE,
                page_size=page_size,
                max_pages=max_pages,
                initial_after=plan.initial_after,
                is_known_unchanged=known_predicate,
                stop_after_unchanged_pages=stop_after_unchanged,
                on_checkpoint=persist_checkpoint,
            )
        except Exception as exc:  # transport/parse failures are per-source, not fatal
            return _failed_poll(source.id, exc)

        # Provider cursors are opaque and can expire. A rejected saved cursor is cleared and
        # retried once from the head so a stale checkpoint can never wedge this source forever.
        if plan.mode == "resume" and search.page_count == 0 and _checkpoint_rejected(search.error):
            provider_state = clear_checkpoint(provider_state)
            if self._checkpoint_sink is not None:
                self._checkpoint_sink(provider_state)
            first_requests = search.request_count
            checkpoint_offset = 0
            try:
                fallback = search_creatives_result(
                    advertiser_id,
                    fetch=_throttled(self._fetch, _RPC_PAGE_DELAY_S, self._sleep),
                    region=US_REGION_CODE,
                    page_size=page_size,
                    max_pages=max_pages,
                    is_known_unchanged=known_predicate,
                    stop_after_unchanged_pages=stop_after_unchanged,
                    on_checkpoint=persist_checkpoint,
                )
                search = fallback.__class__(
                    **{
                        **fallback.__dict__,
                        "request_count": first_requests + fallback.request_count,
                    }
                )
            except Exception as exc:
                return _failed_poll(source.id, exc)

        diagnostics: list[PollDiagnostic] = []
        if search.error is not None:
            diagnostic = classify_exception(
                search.error, provider=GOOGLE_ATC_SOURCE_TYPE, phase="creative_pages"
            )
            diagnostics.append(diagnostic)
            logger.warning(
                "google_pagination_interrupted",
                source_id=source.id,
                stage="google_atc.creative_pages",
                category=diagnostic.category,
                code=diagnostic.code,
                request_count=search.request_count,
                page_count=search.page_count,
                item_count=len(search.creatives),
                traceback=safe_traceback(search.error),
            )
        if (
            search.continuation_remaining
            and search.error is None
            and not search.stopped_after_unchanged
        ):
            diagnostics.append(
                PollDiagnostic(
                    code="google_page_limit_reached",
                    category="request_limit",
                    message=(
                        "Google Ads Transparency still had another page when the configured "
                        "page limit was reached."
                    ),
                    retryable=True,
                    provider=GOOGLE_ATC_SOURCE_TYPE,
                    phase="creative_pages",
                    details={"max_pages": max_pages, "page_size": page_size},
                )
            )
        if not search.creatives and search.error is not None:
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=diagnostics,
                request_count=search.request_count,
                page_count=search.page_count,
                state_updates=provider_state,
                scan_mode=plan.mode,
                resumed=plan.mode == "resume",
                checkpoint_page=plan.prior_page_count,
                stop_reason="provider_error",
            )

        # Known unchanged rows only need a freshness touch; they do not need another payload
        # snapshot or preview request. New/changed/pending-preview creatives flow normally.
        creatives = search.creatives
        verified_external_ids = [
            str(creative["creative_id"])
            for creative in creatives
            if is_known_unchanged(creative, plan.known_index)
            and not preview_needs_refresh(creative, plan.known_index)
        ]
        creatives = [
            creative
            for creative in creatives
            if not is_known_unchanged(creative, plan.known_index)
            or preview_needs_refresh(creative, plan.known_index)
        ]
        preview_requests = 0
        # Once pagination is rejected (especially HTTP 429), make no more provider calls.
        # Successfully fetched pages are still persisted as an explicitly partial result.
        if search.error is None and self._preview_fetch is not None and preview_limit > 0:
            creatives, preview_diagnostics, preview_requests = enrich_preview_artifacts(
                creatives,
                preview_fetch=_throttled(self._preview_fetch, _PREVIEW_FETCH_DELAY_S, self._sleep),
                limit=preview_limit,
                known_index=plan.known_index,
            )
            diagnostics.extend(preview_diagnostics)

        pagination_succeeded = search.error is None and search.complete
        if pagination_succeeded:
            provider_state = after_success(
                provider_state,
                mode=effective_mode,
                reached_provider_end=not search.continuation_remaining,
                now=now,
            )
            if self._checkpoint_sink is not None:
                self._checkpoint_sink(provider_state)

        items = [creative_to_item(source, advertiser_id, c) for c in creatives]
        complete = search.complete and not diagnostics
        outcome = "success" if items else "explicit_empty"
        if not items and search.creatives:
            outcome = "not_modified"
        if not complete:
            outcome = "partial"
        return SourcePollResult(
            source_id=source.id,
            items=items,
            new_watermark=latest_published(items) or state.watermark,
            outcome=outcome,
            complete=complete,
            truncated=search.continuation_remaining and not search.stopped_after_unchanged,
            truncation_reason=(
                "Google pagination was interrupted by a provider error."
                if search.error is not None and search.continuation_remaining
                else (
                    "Configured Google page limit reached before the continuation token ended."
                    if search.continuation_remaining and not search.stopped_after_unchanged
                    else None
                )
            ),
            diagnostics=diagnostics[:20],
            request_count=search.request_count + preview_requests,
            page_count=search.page_count,
            provider_item_count=len(search.creatives),
            verified_external_ids=verified_external_ids,
            state_updates=provider_state,
            scan_mode=plan.mode,
            resumed=plan.mode == "resume",
            checkpoint_page=(
                checkpoint_offset + search.page_count if not pagination_succeeded else None
            ),
            stop_reason=_stop_reason(search),
        )


def _throttled(fn, delay_s: float, sleep: Sleep):
    """Pause ``delay_s`` before every call after the first (per-poll burst limiter)."""
    first = True

    def wrapper(*args, **kwargs):
        nonlocal first
        if not first:
            sleep(delay_s)
        first = False
        return fn(*args, **kwargs)

    return wrapper


def _checkpoint_rejected(error: BaseException | None) -> bool:
    return isinstance(error, HTTPError) and error.code in {400, 404, 410}


def _stop_reason(search) -> str:
    if search.error is not None:
        return "provider_error"
    if search.stopped_after_unchanged:
        return "unchanged_overlap"
    if search.continuation_remaining:
        return "page_limit"
    return "provider_end"


def _failed_poll(source_id: str, exc: BaseException) -> SourcePollResult:
    logger.warning(
        "google_poll_failed",
        source_id=source_id,
        stage="google_atc.creative_pages",
        traceback=safe_traceback(exc),
    )
    return SourcePollResult(
        source_id=source_id,
        outcome="failed",
        complete=False,
        diagnostics=[
            classify_exception(exc, provider=GOOGLE_ATC_SOURCE_TYPE, phase="creative_pages")
        ],
        request_count=1,
    )


def _preview_limit(source: IntelSource) -> int:
    # Video is the primary target. Image creatives carry no preview URL, so they never consume
    # this budget. Set preview_enrichment=false to disable.
    if not _bool_config(source.config.get("preview_enrichment"), default=True):
        return 0
    return _int_config(
        source.config.get("preview_enrichment_limit"), default=400, minimum=0, maximum=1000
    )


def _page_limit_config(config: dict) -> int | None:
    """Return a positive page cap, or ``None`` for explicit 0/null/unlimited."""
    value = config.get("max_pages", 0)
    if value is None or str(value).strip().lower() in {"0", "none", "null", "unlimited"}:
        return None
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return None


def _bool_config(value, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    parsed = str(value).strip().lower()
    if parsed in {"1", "true", "yes", "on"}:
        return True
    if parsed in {"0", "false", "no", "off"}:
        return False
    return default


def _int_config(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
