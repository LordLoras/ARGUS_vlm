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

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

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
DEFAULT_SORT_MODE = "relevancy_monthly_grouped"
DEFAULT_SORT_DIRECTION = "desc"

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

        active_status = _active_status(source.config.get("active_status"), default="active")
        sort_mode = _string_config(source.config.get("sort_mode"), default=DEFAULT_SORT_MODE)
        sort_direction = _sort_direction(source.config.get("sort_direction"))
        scrolls = _int_config(source.config.get("scrolls"), default=20, minimum=0, maximum=200)
        max_cards = _int_config(source.config.get("max_cards"), default=250, minimum=1, maximum=1000)
        wait_ms = _int_config(source.config.get("wait_ms"), default=1800, minimum=250, maximum=15000)
        stop_after_no_new = _int_config(
            source.config.get("stop_after_no_new"), default=3, minimum=0, maximum=20
        )
        headed = bool(source.config.get("headed") or False)
        include_statuses = _status_list(source.config.get("include_statuses"))

        url = source.url or build_meta_ad_library_url(
            page_id,
            active_status=active_status,
            sort_mode=sort_mode,
            sort_direction=sort_direction,
        )
        out_dir = _source_output_dir(self._config.cache_dir, source.id)
        try:
            result = self._probe_runner(
                url=url,
                out_dir=out_dir,
                scrolls=scrolls,
                max_cards=max_cards,
                headed=headed,
                wait_ms=wait_ms,
                stop_after_no_new=stop_after_no_new,
            )
        except Exception as exc:
            return SourcePollResult(source_id=source.id, errors=[str(exc)[:240]])

        cards = [card for card in result.cards if _include_card(card, include_statuses)]
        items = [_card_to_item(source, result.source_url, card) for card in cards]
        return SourcePollResult(
            source_id=source.id,
            items=items,
            new_watermark=_latest_published(items) or state.watermark,
        )


def build_meta_ad_library_url(
    page_id: str,
    *,
    active_status: str = "active",
    sort_mode: str = DEFAULT_SORT_MODE,
    sort_direction: str = DEFAULT_SORT_DIRECTION,
) -> str:
    params = {
        "active_status": _active_status(active_status, default="active"),
        "ad_type": "all",
        "country": "US",
        "is_targeted_country": "false",
        "media_type": "all",
        "search_type": "page",
        "sort_data[mode]": _string_config(sort_mode, default=DEFAULT_SORT_MODE),
        "sort_data[direction]": _sort_direction(sort_direction),
        "view_all_page_id": page_id.strip(),
    }
    return "https://www.facebook.com/ads/library/?" + urlencode(params)


def _card_to_item(source: IntelSource, source_url: str, card) -> RawSourceItem:
    external_id = card.library_id or f"meta_card_{card.index}"
    direct_url = f"https://www.facebook.com/ads/library/?id={external_id}"
    thumbnail_url = _first_present(
        card.image_sources,
        card.video_posters,
        card.background_image_sources,
    )
    return RawSourceItem(
        external_id=external_id,
        url=direct_url,
        canonical_url=direct_url,
        resource_type="meta_ad",
        title=_title_for_card(source.brand_name, external_id),
        description=_creative_copy_for_card(source.brand_name, card.text),
        published_at=_parse_started_running(card.started_running),
        thumbnail_url=thumbnail_url,
        raw={
            "source": META_AD_LIBRARY_SOURCE_TYPE,
            "source_url": source_url,
            "library_id": card.library_id,
            "status": card.status,
            "started_running": card.started_running,
            "platforms": card.platforms,
            "links": card.links,
            "image_sources": card.image_sources,
            "video_sources": card.video_sources,
            "video_posters": card.video_posters,
            "background_image_sources": card.background_image_sources,
            "video_count": card.video_count,
            "creative_variant_count": card.creative_variant_count,
            "has_multiple_versions": card.has_multiple_versions,
            "raw_card_text": card.text,
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


def _title_for_card(brand_name: str, library_id: str | None) -> str:
    if library_id:
        return f"{brand_name} Meta ad {library_id}"
    return f"{brand_name} Meta ad"


def _creative_copy_for_card(brand_name: str, text: str) -> str:
    compact = " ".join((text or "").split())
    if not compact:
        return ""
    marker = f"{brand_name} Sponsored"
    if marker in compact:
        compact = compact.split(marker, 1)[1].strip()
    else:
        brand_marker = re.search(
            rf"\b{re.escape(brand_name)}(?:\s+USA)?\s+Sponsored\b",
            compact,
            flags=re.IGNORECASE,
        )
        if brand_marker:
            compact = compact[brand_marker.end() :].strip()
    compact = re.sub(
        r"\b(?:Active|Inactive)?\s*Library\s+ID[:\s]*[0-9]+\b", " ", compact
    )
    compact = re.sub(
        r"^\s*(?:Active|Inactive)?\s*(?:Low|Medium|High)?\s*impression\s+count\s+"
        r"(?:Impressions:\s*<?[0-9,]+)?\s*(?:See ad)?\s*",
        " ",
        compact,
        flags=re.IGNORECASE,
    )
    compact = re.sub(
        r"\b(?:Low|Medium|High)\s+impression\s+count\b",
        " ",
        compact,
        flags=re.IGNORECASE,
    )
    compact = re.sub(
        r"\bStarted\s+running\s+on\s+.+?(?=\b(?:Platforms|This ad|Open "
        r"Dropdown|See summary|Details)\b|$)",
        " ",
        compact,
        flags=re.IGNORECASE,
    )
    compact = re.sub(
        r"\bThis\s+ad\s+has\s+multiple\s+versions\b.*?\bcreative\s+and\s+text\b",
        " ",
        compact,
        flags=re.IGNORECASE,
    )
    compact = re.sub(
        r"\b(?:Platforms|Open Dropdown|See summary details?|Details)\b",
        " ",
        compact,
        flags=re.IGNORECASE,
    )
    compact = re.sub(r"\b(?:Facebook|Instagram|Messenger|Audience Network|Threads)\b", " ", compact)
    return " ".join(compact.split())


def _source_output_dir(cache_dir: Path, source_id: str) -> Path:
    return cache_dir / "meta_ad_library_ui" / _safe_path_segment(source_id)


def _safe_path_segment(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:120]


def _active_status(value, *, default: str) -> str:
    parsed = str(value or default).strip().lower()
    return parsed if parsed in {"active", "all", "inactive"} else default


def _sort_direction(value) -> str:
    parsed = str(value or DEFAULT_SORT_DIRECTION).strip().lower()
    return parsed if parsed in {"asc", "desc"} else DEFAULT_SORT_DIRECTION


def _string_config(value, *, default: str) -> str:
    parsed = str(value or default).strip()
    if not parsed or len(parsed) > 80:
        return default
    return parsed


def _status_list(value) -> set[str] | None:
    if value is None:
        return None
    raw_values = value if isinstance(value, list) else [value]
    statuses = {str(item).strip().lower() for item in raw_values if str(item).strip()}
    statuses = statuses.intersection({"active", "inactive", "unknown"})
    return statuses or None


def _include_card(card, include_statuses: set[str] | None) -> bool:
    if include_statuses is None:
        return True
    return (card.status or "unknown") in include_statuses


def _int_config(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _latest_published(items: list[RawSourceItem]) -> str | None:
    dates = [item.published_at for item in items if item.published_at is not None]
    return max(dates).isoformat() if dates else None


def _first_present(*groups: list[str]) -> str | None:
    for group in groups:
        if group:
            return group[0]
    return None
