"""YouTube official-channel adapter — feed-first detection + duration enrichment.

Detection uses the **public channel Atom feed**
``https://www.youtube.com/feeds/videos.xml?channel_id=<id>`` — no API key, no quota —
with ETag / Last-Modified conditional requests for incremental polling. This is the
cheapest, ToS-clean way to learn "did this channel upload something new."

The feed carries no **duration**, which is the strongest ad-likelihood cue (ads cluster
at ~5-95s; long-form content is almost never an ad). When a ``YOUTUBE_API_KEY`` is
available we enrich the feed items with a single Data-API ``videos.list`` call
(``part=contentDetails``, ≈1 quota unit per ≤50 ids) to fill ``duration_ms``. Enrichment
is best-effort: any failure (no key, network, quota, malformed JSON) leaves duration
unset and the ad-gate falls back to keyword-only.

Both network channels are injected (``http`` for the feed, ``json_http`` for the Data
API) so the adapter is fully testable offline. When the feed fetcher is injected (tests),
the Data-API client defaults to **disabled** unless one is injected too — so a machine
that happens to hold a real key never makes a live call from a unit test.
"""

from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime

import structlog

from ad_classifier._env import resolve_api_key
from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.diagnostics import (
    classify_exception,
    configuration_diagnostic,
    http_status_diagnostic,
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
from ad_classifier.intelligence_crawler.timeutils import parse_iso

logger = structlog.get_logger(__name__)

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
_FEED_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_VIDEOS_LIST_TEMPLATE = (
    "https://www.googleapis.com/youtube/v3/videos?part=contentDetails&id={ids}&key={key}"
)
_VIDEOS_LIST_BATCH = 50  # Data API caps the id list at 50 per call
_DEFAULT_API_KEY_ENV = "YOUTUBE_API_KEY"
# ISO 8601 duration as returned by contentDetails.duration, e.g. "PT1M35S", "PT1H2M3S".
_ISO8601_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)


@dataclass(frozen=True)
class FeedResponse:
    status_code: int
    body: str
    etag: str | None = None
    last_modified: str | None = None


# (url, request_headers) -> FeedResponse. Injected so tests need no network.
FeedFetcher = Callable[[str, dict[str, str]], FeedResponse]
# url -> parsed JSON dict (Data API videos.list). Injected so enrichment is testable offline.
JsonFetcher = Callable[[str], dict]


@register_source("youtube_channel")
class YouTubeChannelAdapter:
    tier: Tier = "C"

    def __init__(
        self,
        *,
        http: FeedFetcher | None = None,
        intel_config: IntelConfig | None = None,
        json_http: JsonFetcher | None = None,
        api_key: str | None = None,
    ) -> None:
        self._fetch: FeedFetcher = http or _default_fetch
        self._config = intel_config
        self._api_key = api_key
        # The Data-API client shares the feed's network posture: when the feed fetcher is
        # injected (tests/offline) we do NOT silently fall back to a live call — enrichment
        # stays disabled unless a json client is injected too.
        if json_http is not None:
            self._json_fetch: JsonFetcher | None = json_http
        elif http is None:
            self._json_fetch = _default_json_fetch  # production default
        else:
            self._json_fetch = None

    def poll(self, source: IntelSource, state: SourceState, *, now: datetime) -> SourcePollResult:
        feed_url = source.url or _feed_url(source.platform_id)
        if not feed_url:
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=[
                    configuration_diagnostic(
                        "youtube_channel_id_missing",
                        "YouTube source needs a channel ID or feed URL.",
                        provider="youtube_channel",
                    )
                ],
            )

        headers: dict[str, str] = {}
        if state.etag:
            headers["If-None-Match"] = state.etag
        if state.last_modified:
            headers["If-Modified-Since"] = state.last_modified

        try:
            response = self._fetch(feed_url, headers)
        except Exception as exc:  # transport/parse failures are per-source, not fatal
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=[
                    classify_exception(exc, provider="youtube_channel", phase="feed_fetch")
                ],
                request_count=1,
            )

        if response.status_code == 304:  # not modified since last poll
            return SourcePollResult(
                source_id=source.id,
                items=[],
                new_watermark=state.watermark,
                etag=state.etag,
                last_modified=state.last_modified,
                outcome="not_modified",
                request_count=1,
                page_count=1,
            )
        if response.status_code >= 400:
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=[
                    http_status_diagnostic(response.status_code, provider="youtube_channel")
                ],
                request_count=1,
            )

        try:
            items = _parse_feed(response.body)
        except Exception as exc:
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=[
                    classify_exception(exc, provider="youtube_channel", phase="feed_parse")
                ],
                request_count=1,
                page_count=1,
            )
        enrichment_diagnostics, enrichment_requests = self._enrich_durations(source, items)
        watermark = _latest_published(items) or state.watermark
        complete = not enrichment_diagnostics
        return SourcePollResult(
            source_id=source.id,
            items=items,
            new_watermark=watermark,
            etag=response.etag or state.etag,
            last_modified=response.last_modified or state.last_modified,
            outcome=(
                "partial" if enrichment_diagnostics else ("success" if items else "explicit_empty")
            ),
            complete=complete,
            diagnostics=enrichment_diagnostics,
            request_count=1 + enrichment_requests,
            page_count=1,
            provider_item_count=len(items),
        )

    def _enrich_durations(
        self, source: IntelSource, items: list[RawSourceItem]
    ) -> tuple[list[PollDiagnostic], int]:
        """Fill ``duration_ms`` on feed items via the Data-API ``videos.list``.

        Best-effort and never raises into ``poll``: on any failure the items keep
        ``duration_ms=None`` and the ad-gate falls back to its keyword-only signal.
        """
        if self._json_fetch is None or not items:
            return [], 0
        env_name = str(source.config.get("api_key_env") or _DEFAULT_API_KEY_ENV)
        api_key = self._api_key or resolve_api_key(env_name)
        if not api_key:  # no key configured → keyword-only gate (documented fallback)
            return [], 0

        by_id = {item.external_id: item for item in items}
        durations: dict[str, int] = {}
        request_count = 0
        for batch in _batched(list(by_id), _VIDEOS_LIST_BATCH):
            url = _VIDEOS_LIST_TEMPLATE.format(ids=",".join(batch), key=api_key)
            try:
                request_count += 1
                payload = self._json_fetch(url)
            except Exception as exc:  # network/quota/transport — keep keyword-only gate
                base = classify_exception(
                    exc, provider="youtube_channel", phase="duration_enrichment"
                )
                logger.warning(
                    "youtube_enrich_failed",
                    source_id=source.id,
                    stage="duration_enrichment",
                    error_category=base.category,
                )
                return [
                    base.model_copy(
                        update={
                            "code": "youtube_duration_enrichment_failed",
                            "category": "asset_fetch",
                            "message": "YouTube duration enrichment failed; feed items were retained.",
                            "details": {"cause_category": base.category},
                        }
                    )
                ], request_count
            durations.update(_parse_durations(payload))

        for vid, ms in durations.items():
            item = by_id.get(vid)
            if item is not None:
                item.duration_ms = ms
        return [], request_count


def _feed_url(channel_id: str | None) -> str | None:
    channel_id = (channel_id or "").strip()
    return _FEED_TEMPLATE.format(channel_id=channel_id) if channel_id else None


def _parse_feed(body: str) -> list[RawSourceItem]:
    root = ET.fromstring(body)
    if root.tag.split("}", 1)[-1] != "feed":
        raise ValueError("YouTube feed response did not contain an Atom feed root.")
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


def _parse_durations(payload: dict) -> dict[str, int]:
    """Map video id -> duration_ms from a ``videos.list`` JSON payload."""
    out: dict[str, int] = {}
    for entry in payload.get("items", []) or []:
        if not isinstance(entry, dict):
            continue
        vid = entry.get("id")
        content_details = entry.get("contentDetails") or {}
        iso = content_details.get("duration") if isinstance(content_details, dict) else None
        ms = _duration_to_ms(iso) if isinstance(iso, str) else None
        if isinstance(vid, str) and ms is not None:
            out[vid] = ms
    return out


def _duration_to_ms(value: str) -> int | None:
    """Parse an ISO 8601 duration (``PT1M35S``) to milliseconds; None if unparseable."""
    match = _ISO8601_DURATION.fullmatch(value.strip())
    if match is None:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total_seconds = ((days * 24 + hours) * 60 + minutes) * 60 + seconds
    return total_seconds * 1000


def _batched(seq: list[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(seq), size):
        yield seq[start : start + size]


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


def _default_json_fetch(url: str) -> dict:  # pragma: no cover - network
    request = urllib.request.Request(
        url, headers={"User-Agent": "ARGUS-IntelligenceCrawler/0.1"}, method="GET"
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        body = response.read(2_000_000).decode("utf-8", errors="replace")
    return json.loads(body)
