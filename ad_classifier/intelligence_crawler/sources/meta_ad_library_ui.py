"""Meta Ad Library public-UI source adapter.

This adapter is deliberately conservative: it observes the public Ad Library page for a
verified brand page id and converts visible cards into ``RawSourceItem`` records. It does
not log in, click ads, replay hidden API endpoints, or write directly to the DB.

Production semantics come from the runner:
- first poll is baseline-only;
- new library ids after activation become live candidates;
- repeated ids are idempotent.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.meta_ad_library_probe import (
    MetaProbeResult,
    run_meta_ad_library_probe,
)
from ad_classifier.intelligence_crawler.models import (
    IntelSource,
    RawSourceItem,
    SourcePollResult,
    SourceState,
    Tier,
)
from ad_classifier.intelligence_crawler.sources.base import register_source
from ad_classifier.intelligence_crawler.timeutils import parse_iso

META_AD_LIBRARY_SOURCE_TYPE = "meta_ad_library_ui"

ProbeRunner = Callable[..., MetaProbeResult]


@register_source(META_AD_LIBRARY_SOURCE_TYPE)
class MetaAdLibraryUiAdapter:
    """Observe public Meta Ad Library cards for a configured page id."""

    tier: Tier = "B"

    def __init__(
        self,
        *,
        http=None,
        intel_config: IntelConfig | None = None,
        probe_runner: ProbeRunner = run_meta_ad_library_probe,
    ) -> None:
        self._config = intel_config or IntelConfig()
        self._probe_runner = probe_runner

    def poll(self, source: IntelSource, state: SourceState, *, now: datetime) -> SourcePollResult:
        page_id = (source.platform_id or "").strip()
        if not page_id:
            return SourcePollResult(
                source_id=source.id,
                errors=["meta_ad_library_ui source needs platform_id set to the Meta page id"],
            )

        active_status = str(source.config.get("active_status") or "all")
        if active_status not in {"active", "all", "inactive"}:
            active_status = "all"
        scrolls = _int_config(source.config.get("scrolls"), default=4, minimum=0, maximum=50)
        max_cards = _int_config(source.config.get("max_cards"), default=40, minimum=1, maximum=250)
        wait_ms = _int_config(source.config.get("wait_ms"), default=1800, minimum=250, maximum=15000)
        headed = bool(source.config.get("headed") or False)

        url = source.url or build_meta_ad_library_url(page_id, active_status=active_status)
        out_dir = _source_output_dir(self._config.cache_dir, source.id)
        try:
            result = self._probe_runner(
                url=url,
                out_dir=out_dir,
                scrolls=scrolls,
                max_cards=max_cards,
                headed=headed,
                wait_ms=wait_ms,
            )
        except Exception as exc:
            return SourcePollResult(source_id=source.id, errors=[str(exc)[:240]])

        items = [_card_to_item(source, result.source_url, card) for card in result.cards]
        return SourcePollResult(
            source_id=source.id,
            items=items,
            new_watermark=_latest_published(items) or state.watermark,
        )


def build_meta_ad_library_url(page_id: str, *, active_status: str = "all") -> str:
    safe_status = active_status if active_status in {"active", "all", "inactive"} else "all"
    return (
        "https://www.facebook.com/ads/library/"
        f"?active_status={safe_status}&ad_type=all&country=US&is_targeted_country=false"
        "&media_type=all&search_type=page&sort_data[mode]=total_impressions"
        f"&sort_data[direction]=desc&view_all_page_id={page_id}"
    )


def _card_to_item(source: IntelSource, source_url: str, card) -> RawSourceItem:
    external_id = card.library_id or f"meta_card_{card.index}"
    direct_url = f"https://www.facebook.com/ads/library/?id={external_id}"
    return RawSourceItem(
        external_id=external_id,
        url=direct_url,
        canonical_url=direct_url,
        resource_type="meta_ad",
        title=_title_for_card(source.brand_name, card.text),
        description=card.text,
        published_at=_parse_started_running(card.started_running),
        thumbnail_url=card.image_sources[0] if card.image_sources else None,
        raw={
            "source": META_AD_LIBRARY_SOURCE_TYPE,
            "source_url": source_url,
            "library_id": card.library_id,
            "status": card.status,
            "started_running": card.started_running,
            "platforms": card.platforms,
            "links": card.links,
            "image_sources": card.image_sources,
            "video_count": card.video_count,
            "screenshot_path": card.screenshot_path,
            "rect": card.rect,
        },
    )


def _parse_started_running(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parse_iso(value)
    except ValueError:
        parsed = None
    if parsed is not None:
        return parsed
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _title_for_card(brand_name: str, text: str) -> str:
    compact = " ".join((text or "").split())
    if not compact:
        return f"{brand_name} Meta ad"
    # Remove the mechanical card header if present and keep the creative-facing copy.
    marker = f"{brand_name} Sponsored"
    if marker in compact:
        compact = compact.split(marker, 1)[1].strip()
    return f"{brand_name}: {compact[:180]}"


def _source_output_dir(cache_dir: Path, source_id: str) -> Path:
    return cache_dir / "meta_ad_library_ui" / _safe_path_segment(source_id)


def _safe_path_segment(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:120]


def _int_config(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _latest_published(items: list[RawSourceItem]) -> str | None:
    dates = [item.published_at for item in items if item.published_at is not None]
    return max(dates).isoformat() if dates else None
