"""RSS / sitemap / newsroom adapter (SKELETON — runbook Phase 4, not yet implemented).

Planned design:
- Parse RSS/Atom feeds and XML sitemaps from brand US newsrooms and US trade press.
- Stable ``external_id`` from the item GUID, else a canonical-URL hash (never NULL).
- Incremental via ETag/Last-Modified + GUID/content-hash watermarking.
- Honor the robots gate + rate limiter before any HTTP fetch.

Registered so the type is visible; ``poll`` raises until implemented. Disabled by
default in config.
"""

from __future__ import annotations

from datetime import datetime

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.models import (
    IntelSource,
    SourcePollResult,
    SourceState,
    Tier,
)
from ad_classifier.intelligence_crawler.sources.base import register_source


@register_source("rss")
class RssAdapter:
    tier: Tier = "B"

    def __init__(self, *, http=None, intel_config: IntelConfig | None = None) -> None:
        self._http = http
        self._config = intel_config

    def poll(self, source: IntelSource, state: SourceState, *, now: datetime) -> SourcePollResult:
        raise NotImplementedError(
            "RssAdapter is a Phase 4 stub. Implement RSS/Atom + sitemap parsing with "
            "GUID/canonical-URL dedup and the robots/rate-limit gate. See docs/ runbook §7 Phase 4."
        )
