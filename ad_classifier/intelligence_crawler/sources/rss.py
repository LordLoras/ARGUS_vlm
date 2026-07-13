"""RSS / Atom newsroom & trade-press adapter (Phase 4).

Parses RSS 2.0 and Atom feeds into RawSourceItems. Stable ``external_id`` from the item
GUID / Atom id, else the canonical link, else a title+date hash (never empty). The default
network path is **robots-gated + rate-limited** (``sources/http.py``); the fetcher is
injectable so the adapter is fully offline-testable.
"""

from __future__ import annotations

import email.utils
import xml.etree.ElementTree as ET
from datetime import datetime

import structlog

from ad_classifier.entity_graph.utils import digest, normalize_name
from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.diagnostics import (
    classify_exception,
    configuration_diagnostic,
    http_status_diagnostic,
)
from ad_classifier.intelligence_crawler.models import (
    IntelSource,
    RawSourceItem,
    SourcePollResult,
    SourceState,
    Tier,
)
from ad_classifier.intelligence_crawler.sources.base import register_source
from ad_classifier.intelligence_crawler.sources.http import DefaultHttpFetcher, HttpFetcher
from ad_classifier.intelligence_crawler.timeutils import parse_iso

logger = structlog.get_logger(__name__)

_ATOM = {"atom": "http://www.w3.org/2005/Atom"}


@register_source("rss")
class RssAdapter:
    tier: Tier = "C"

    def __init__(
        self, *, http: HttpFetcher | None = None, intel_config: IntelConfig | None = None
    ) -> None:
        self._config = intel_config
        self._fetch: HttpFetcher = http or _build_default_fetcher(intel_config)

    def poll(self, source: IntelSource, state: SourceState, *, now: datetime) -> SourcePollResult:
        if not source.url:
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=[
                    configuration_diagnostic(
                        "rss_feed_url_missing",
                        "RSS source needs a feed URL.",
                        provider="rss",
                    )
                ],
            )

        headers: dict[str, str] = {}
        if state.etag:
            headers["If-None-Match"] = state.etag
        if state.last_modified:
            headers["If-Modified-Since"] = state.last_modified

        try:
            response = self._fetch(source.url, headers)
        except Exception as exc:  # robots-blocked / transport: per-source, not fatal
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=[classify_exception(exc, provider="rss", phase="feed_fetch")],
                request_count=1,
            )

        if response.status_code == 304:
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
                diagnostics=[http_status_diagnostic(response.status_code, provider="rss")],
                request_count=1,
            )

        try:
            items = _parse_feed(response.body)
        except Exception as exc:
            return SourcePollResult(
                source_id=source.id,
                outcome="failed",
                complete=False,
                diagnostics=[classify_exception(exc, provider="rss", phase="feed_parse")],
                request_count=1,
                page_count=1,
            )
        watermark = _latest_published(items) or state.watermark
        return SourcePollResult(
            source_id=source.id,
            items=items,
            new_watermark=watermark,
            etag=response.etag or state.etag,
            last_modified=response.last_modified or state.last_modified,
            outcome="success" if items else "explicit_empty",
            request_count=1,
            page_count=1,
            provider_item_count=len(items),
        )


def _build_default_fetcher(config: IntelConfig | None) -> HttpFetcher:
    http = config.http if config is not None else None
    return DefaultHttpFetcher(
        user_agent=http.user_agent if http else "ARGUS-IntelligenceCrawler/0.1",
        timeout_s=http.timeout_s if http else 12.0,
        rate_limit_per_minute=http.rate_limit_per_minute if http else 20,
        respect_robots=http.respect_robots_txt if http else True,
        max_bytes=http.max_page_bytes if http else 2_000_000,
    ).fetch


def _parse_feed(body: str) -> list[RawSourceItem]:
    root = ET.fromstring(body)
    tag = _localname(root.tag)
    if tag == "rss":
        return _parse_rss(root)
    if tag == "feed":
        return _parse_atom(root)
    raise ValueError(f"unsupported feed root element: {tag}")


def _parse_rss(root: ET.Element) -> list[RawSourceItem]:
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[RawSourceItem] = []
    for item in channel.findall("item"):
        link = _text(item.find("link"))
        guid = _text(item.find("guid"))
        url = link or guid
        if not url:
            continue
        title = _text(item.find("title"))
        published = _parse_rfc822(_text(item.find("pubDate")))
        items.append(
            RawSourceItem(
                external_id=guid or link or _fallback_id(title, published),
                url=url,
                resource_type="press",
                title=title,
                description=_text(item.find("description")),
                published_at=published,
                raw={"source": "rss"},
            )
        )
    return items


def _parse_atom(root: ET.Element) -> list[RawSourceItem]:
    items: list[RawSourceItem] = []
    for entry in root.findall("atom:entry", _ATOM):
        atom_id = _text(entry.find("atom:id", _ATOM))
        link = _atom_link(entry)
        url = link or atom_id
        if not url:
            continue
        title = _text(entry.find("atom:title", _ATOM))
        published = parse_iso(
            _text(entry.find("atom:published", _ATOM)) or _text(entry.find("atom:updated", _ATOM))
        )
        items.append(
            RawSourceItem(
                external_id=atom_id or link or _fallback_id(title, published),
                url=url,
                resource_type="press",
                title=title,
                description=_text(entry.find("atom:summary", _ATOM))
                or _text(entry.find("atom:content", _ATOM)),
                published_at=published,
                raw={"source": "atom"},
            )
        )
    return items


def _atom_link(entry: ET.Element) -> str | None:
    fallback = None
    for link in entry.findall("atom:link", _ATOM):
        href = link.get("href")
        if not href:
            continue
        if link.get("rel") in (None, "alternate"):
            return href
        fallback = fallback or href
    return fallback


def _fallback_id(title: str | None, published: datetime | None) -> str:
    key = digest(normalize_name(title or ""), published.isoformat() if published else "")
    return f"rss_{key[:20]}"


def _parse_rfc822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _localname(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    return element.text.strip() or None


def _latest_published(items: list[RawSourceItem]) -> str | None:
    published = [item.published_at for item in items if item.published_at is not None]
    return max(published).isoformat() if published else None
