"""YouTube official-channel adapter — feed-first detection (Phase 3).

Detection uses the **public channel Atom feed**
``https://www.youtube.com/feeds/videos.xml?channel_id=<id>`` — no API key, no quota —
with ETag / Last-Modified conditional requests for incremental polling. This is the
cheapest, ToS-clean way to learn "did this channel upload something new."

Data-API enrichment (``videos.list`` for duration/tags behind ``YOUTUBE_API_KEY``) is a
documented follow-up hook (``_ENRICHMENT_TODO``); detection works fully without a key.

Network is injected (``http``) so the adapter is fully testable offline.
"""

from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import structlog

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.models import (
    IntelSource,
    RawSourceItem,
    SourcePollResult,
    SourceState,
    Tier,
)
from ad_classifier.intelligence_crawler.sources.base import register_source
from ad_classifier.intelligence_crawler.timeutils import parse_iso

logger = structlog.get_logger(__name__)

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
_FEED_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_ENRICHMENT_TODO = "videos.list duration/tags enrichment behind YOUTUBE_API_KEY (Phase 3 follow-up)"


@dataclass(frozen=True)
class FeedResponse:
    status_code: int
    body: str
    etag: str | None = None
    last_modified: str | None = None


# (url, request_headers) -> FeedResponse. Injected so tests need no network.
FeedFetcher = Callable[[str, dict[str, str]], FeedResponse]


@register_source("youtube_channel")
class YouTubeChannelAdapter:
    tier: Tier = "A"

    def __init__(
        self, *, http: FeedFetcher | None = None, intel_config: IntelConfig | None = None
    ) -> None:
        self._fetch: FeedFetcher = http or _default_fetch
        self._config = intel_config

    def poll(self, source: IntelSource, state: SourceState, *, now: datetime) -> SourcePollResult:
        feed_url = source.url or _feed_url(source.platform_id)
        if not feed_url:
            return SourcePollResult(
                source_id=source.id,
                errors=["youtube source needs a platform_id (channel id) or a feed url"],
            )

        headers: dict[str, str] = {}
        if state.etag:
            headers["If-None-Match"] = state.etag
        if state.last_modified:
            headers["If-Modified-Since"] = state.last_modified

        try:
            response = self._fetch(feed_url, headers)
        except Exception as exc:  # transport/parse failures are per-source, not fatal
            return SourcePollResult(source_id=source.id, errors=[str(exc)[:240]])

        if response.status_code == 304:  # not modified since last poll
            return SourcePollResult(
                source_id=source.id,
                items=[],
                new_watermark=state.watermark,
                etag=state.etag,
                last_modified=state.last_modified,
            )
        if response.status_code >= 400:
            return SourcePollResult(
                source_id=source.id, errors=[f"feed fetch returned HTTP {response.status_code}"]
            )

        items = _parse_feed(response.body)
        watermark = _latest_published(items) or state.watermark
        return SourcePollResult(
            source_id=source.id,
            items=items,
            new_watermark=watermark,
            etag=response.etag or state.etag,
            last_modified=response.last_modified or state.last_modified,
        )


def _feed_url(channel_id: str | None) -> str | None:
    channel_id = (channel_id or "").strip()
    return _FEED_TEMPLATE.format(channel_id=channel_id) if channel_id else None


def _parse_feed(body: str) -> list[RawSourceItem]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    items: list[RawSourceItem] = []
    for entry in root.findall("atom:entry", _NS):
        vid = _text(entry.find("yt:videoId", _NS))
        if not vid:
            continue
        url = _alternate_link(entry) or f"https://www.youtube.com/watch?v={vid}"
        group = entry.find("media:group", _NS)
        description = _text(group.find("media:description", _NS)) if group is not None else None
        thumbnail_el = group.find("media:thumbnail", _NS) if group is not None else None
        items.append(
            RawSourceItem(
                external_id=vid,
                url=url,
                resource_type="video",
                title=_text(entry.find("atom:title", _NS)),
                description=description,
                published_at=parse_iso(_text(entry.find("atom:published", _NS))),
                thumbnail_url=thumbnail_el.get("url") if thumbnail_el is not None else None,
                raw={"source": "youtube_feed"},
            )
        )
    return items


def _alternate_link(entry: ET.Element) -> str | None:
    for link in entry.findall("atom:link", _NS):
        if link.get("rel") == "alternate" and link.get("href"):
            return link.get("href")
    return None


def _text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    return element.text.strip() or None


def _latest_published(items: list[RawSourceItem]) -> str | None:
    published = [item.published_at for item in items if item.published_at is not None]
    return max(published).isoformat() if published else None


def _default_fetch(url: str, headers: dict[str, str]) -> FeedResponse:  # pragma: no cover - network
    request = urllib.request.Request(
        url, headers={"User-Agent": "ARGUS-IntelligenceCrawler/0.1", **headers}, method="GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read(2_000_000).decode("utf-8", errors="replace")
            return FeedResponse(
                status_code=int(getattr(response, "status", 200)),
                body=body,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return FeedResponse(status_code=304, body="")
        return FeedResponse(status_code=int(exc.code), body="")
