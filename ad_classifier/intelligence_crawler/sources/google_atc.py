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
from datetime import UTC, datetime

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
    parse_preview_artifacts,
    search_creatives_result,
)
from ad_classifier.intelligence_crawler.models import (
    IntelSource,
    PollDiagnostic,
    RawSourceItem,
    SourcePollResult,
    SourceState,
    Tier,
)
from ad_classifier.intelligence_crawler.sources.base import register_source

logger = structlog.get_logger(__name__)

GOOGLE_ATC_SOURCE_TYPE = "google_atc"
_ADVERTISER_URL = "https://adstransparency.google.com/advertiser/{adv}?region=US"
_CREATIVE_URL = "https://adstransparency.google.com/advertiser/{adv}/creative/{cid}?region=US"
# Politeness pauses between consecutive live requests. An uncapped poll can make hundreds
# of RPC pages and preview fetches; an unthrottled burst earns an HTTP 429.
_RPC_PAGE_DELAY_S = 0.75
_PREVIEW_FETCH_DELAY_S = 0.4

Sleep = Callable[[float], None]


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
        try:
            search = search_creatives_result(
                advertiser_id,
                fetch=_throttled(self._fetch, _RPC_PAGE_DELAY_S, self._sleep),
                region=US_REGION_CODE,
                page_size=page_size,
                max_pages=max_pages,
            )
        except Exception as exc:  # transport/parse failures are per-source, not fatal
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
        if search.continuation_remaining and search.error is None:
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
            )

        creatives = search.creatives
        preview_requests = 0
        # Once pagination is rejected (especially HTTP 429), make no more provider calls.
        # Successfully fetched pages are still persisted as an explicitly partial result.
        if search.error is None and self._preview_fetch is not None and preview_limit > 0:
            creatives, preview_diagnostics, preview_requests = _enrich_preview_artifacts(
                creatives,
                preview_fetch=_throttled(self._preview_fetch, _PREVIEW_FETCH_DELAY_S, self._sleep),
                limit=preview_limit,
            )
            diagnostics.extend(preview_diagnostics)

        items = [_creative_to_item(source, advertiser_id, c) for c in creatives]
        complete = search.complete and not diagnostics
        outcome = "success" if items else "explicit_empty"
        if not complete:
            outcome = "partial"
        return SourcePollResult(
            source_id=source.id,
            items=items,
            new_watermark=_latest_published(items) or state.watermark,
            outcome=outcome,
            complete=complete,
            truncated=search.continuation_remaining,
            truncation_reason=(
                "Google pagination was interrupted by a provider error."
                if search.error is not None and search.continuation_remaining
                else (
                    "Configured Google page limit reached before the continuation token ended."
                    if search.continuation_remaining
                    else None
                )
            ),
            diagnostics=diagnostics[:20],
            request_count=search.request_count + preview_requests,
            page_count=search.page_count,
            provider_item_count=len(search.creatives),
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


def _creative_to_item(source: IntelSource, advertiser_id: str, creative: dict) -> RawSourceItem:
    cid = creative["creative_id"]
    adv = creative.get("advertiser_id") or advertiser_id
    url = _CREATIVE_URL.format(adv=adv, cid=cid)
    raw_advertiser_name = creative.get("advertiser_name")
    advertiser_name = _display_advertiser_name(raw_advertiser_name, source.brand_name)
    # `preview_artifacts` is a dict only when the preview was actually fetched (possibly empty);
    # absent when enrichment was skipped (budget/disabled) — the two must be distinguished.
    preview_fetched = isinstance(creative.get("preview_artifacts"), dict)
    preview_artifacts = creative.get("preview_artifacts")
    preview_artifacts = preview_artifacts if isinstance(preview_artifacts, dict) else {}
    # Inline image comes straight from the RPC (field 3.3.2) — no fetch needed. Merge it with
    # anything the (best-effort) preview fetch found for hosted/video creatives.
    inline_images = _list_artifact(creative, "image_sources")
    image_sources = _dedupe_str(
        [*inline_images, *_list_artifact(preview_artifacts, "image_sources")]
    )
    video_sources = _list_artifact(preview_artifacts, "video_sources")
    video_posters = _list_artifact(preview_artifacts, "video_posters")
    thumbnail_url = _first_present(video_posters, image_sources)
    # Dynamic = we fetched the preview and it yielded no static image or video → a rich-media /
    # HTML5 banner the ad server renders at run time. A video we simply didn't enrich is NOT
    # dynamic, so require preview_fetched (not just the presence of a preview_url).
    dynamic_creative = (
        preview_fetched
        and bool(creative.get("preview_url"))
        and not image_sources
        and not video_sources
    )
    display_format = "rich_media" if dynamic_creative else creative.get("format")
    return RawSourceItem(
        external_id=cid,
        url=url,
        canonical_url=url,
        resource_type="atc_ad",
        title=f"{advertiser_name} ATC creative {cid}",
        description=_creative_description(creative.get("text")),
        published_at=_epoch_to_dt(creative.get("first_shown")),
        thumbnail_url=thumbnail_url,
        raw={
            "source": GOOGLE_ATC_SOURCE_TYPE,
            "advertiser_id": adv,
            "advertiser_name": advertiser_name,
            "advertiser_name_raw": (
                raw_advertiser_name if raw_advertiser_name != advertiser_name else None
            ),
            "advertiser_url": _ADVERTISER_URL.format(adv=adv),
            "format_code": creative.get("format_code"),
            "format": display_format,
            "first_shown": creative.get("first_shown"),
            "last_shown": creative.get("last_shown"),
            "preview_url": creative.get("preview_url"),
            "region": "US",
            "has_inline_image": bool(inline_images),
            "dynamic_creative": dynamic_creative,
            "preview_enriched": bool(preview_artifacts),
            "youtube_video_ids": _list_artifact(preview_artifacts, "youtube_video_ids"),
            "image_sources": image_sources,
            "video_sources": video_sources,
            "video_posters": video_posters,
            "links": _links_artifact(preview_artifacts),
        },
    )


def _enrich_preview_artifacts(
    creatives: list[dict], *, preview_fetch: PreviewFetch, limit: int
) -> tuple[list[dict], list[PollDiagnostic], int]:
    enriched: list[dict] = []
    diagnostics: list[PollDiagnostic] = []
    fetched = 0
    for creative in creatives:
        next_creative = dict(creative)
        preview_url = str(next_creative.get("preview_url") or "").strip()
        if preview_url and fetched < limit:
            fetched += 1
            try:
                script = preview_fetch(preview_url)
                next_creative["preview_artifacts"] = parse_preview_artifacts(
                    script, preview_url=preview_url
                )
            except Exception as exc:
                diagnostic = classify_exception(
                    exc, provider=GOOGLE_ATC_SOURCE_TYPE, phase="preview_asset"
                )
                diagnostics.append(
                    diagnostic.model_copy(
                        update={
                            "code": "google_preview_asset_fetch_failed",
                            "category": "asset_fetch",
                            "message": (
                                "Google preview asset fetch failed for creative "
                                f"{creative.get('creative_id')}."
                            ),
                            "details": {"cause_category": diagnostic.category},
                        }
                    )
                )
        enriched.append(next_creative)
    return enriched, diagnostics, fetched


def _failed_poll(source_id: str, exc: BaseException) -> SourcePollResult:
    return SourcePollResult(
        source_id=source_id,
        outcome="failed",
        complete=False,
        diagnostics=[
            classify_exception(exc, provider=GOOGLE_ATC_SOURCE_TYPE, phase="creative_pages")
        ],
        request_count=1,
    )


def _epoch_to_dt(value: int | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _latest_published(items: list[RawSourceItem]) -> str | None:
    dates = [item.published_at for item in items if item.published_at is not None]
    return max(dates).isoformat() if dates else None


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


def _list_artifact(artifacts: dict, key: str) -> list[str]:
    values = artifacts.get(key)
    if not isinstance(values, list):
        return []
    return [str(value).strip() for value in values if str(value or "").strip()]


def _links_artifact(artifacts: dict) -> list[dict[str, str]]:
    values = artifacts.get("links")
    if not isinstance(values, list):
        return []
    links: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        href = str(value.get("href") or "").strip()
        text = str(value.get("text") or "Link").strip()
        if href:
            links.append({"text": text, "href": href})
    return links


def _first_present(*groups: list[str]) -> str | None:
    for group in groups:
        if group:
            return group[0]
    return None


def _dedupe_str(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _creative_description(text: object) -> str | None:
    """Ad copy recovered from the inline creative HTML (empty for image-only creatives)."""
    if not isinstance(text, str):
        return None
    clean = " ".join(text.split()).strip()
    return clean[:600] or None


def _display_advertiser_name(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    if not text or "\ufffd" in text:
        return fallback
    return text
