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

from datetime import UTC, datetime

import structlog

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.google_atc_rpc import (
    US_REGION_CODE,
    RpcFetch,
    default_rpc_fetch,
    search_creatives,
)
from ad_classifier.intelligence_crawler.models import (
    IntelSource,
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
    ) -> None:
        self._config = intel_config or IntelConfig()
        if rpc_fetch is not None:
            self._fetch: RpcFetch | None = rpc_fetch
        elif http is None:
            self._fetch = default_rpc_fetch  # production default
        else:
            self._fetch = None  # injected feed client → no implicit network

    def poll(self, source: IntelSource, state: SourceState, *, now: datetime) -> SourcePollResult:
        advertiser_id = (source.platform_id or "").strip()
        if not advertiser_id:
            return SourcePollResult(
                source_id=source.id,
                errors=["google_atc source needs platform_id set to the ATC advertiser id (AR...)"],
            )
        if self._fetch is None:  # pragma: no cover - guarded construction
            return SourcePollResult(source_id=source.id, errors=["no ATC rpc client available"])

        page_size = _int_config(source.config.get("page_size"), default=40, minimum=1, maximum=100)
        max_pages = _int_config(source.config.get("max_pages"), default=10, minimum=1, maximum=50)
        try:
            creatives = search_creatives(
                advertiser_id,
                fetch=self._fetch,
                region=US_REGION_CODE,
                page_size=page_size,
                max_pages=max_pages,
            )
        except Exception as exc:  # transport/parse failures are per-source, not fatal
            return SourcePollResult(source_id=source.id, errors=[str(exc)[:240]])

        items = [_creative_to_item(source, advertiser_id, c) for c in creatives]
        return SourcePollResult(
            source_id=source.id,
            items=items,
            new_watermark=_latest_published(items) or state.watermark,
        )


def _creative_to_item(source: IntelSource, advertiser_id: str, creative: dict) -> RawSourceItem:
    cid = creative["creative_id"]
    adv = creative.get("advertiser_id") or advertiser_id
    url = _CREATIVE_URL.format(adv=adv, cid=cid)
    advertiser_name = creative.get("advertiser_name") or source.brand_name
    return RawSourceItem(
        external_id=cid,
        url=url,
        canonical_url=url,
        resource_type="atc_ad",
        title=f"{advertiser_name} ATC creative {cid}",
        description=None,
        published_at=_epoch_to_dt(creative.get("first_shown")),
        thumbnail_url=None,
        raw={
            "source": GOOGLE_ATC_SOURCE_TYPE,
            "advertiser_id": adv,
            "advertiser_name": advertiser_name,
            "advertiser_url": _ADVERTISER_URL.format(adv=adv),
            "format_code": creative.get("format_code"),
            "format": creative.get("format"),
            "first_shown": creative.get("first_shown"),
            "last_shown": creative.get("last_shown"),
            "preview_url": creative.get("preview_url"),
            "region": "US",
        },
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


def _int_config(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
