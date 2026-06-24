"""YouTube official-channel adapter (SKELETON — runbook Phase 3, not yet implemented).

Planned design (intentionally feed-first to avoid API quota):
- Detection: poll the public channel Atom feed
  ``https://www.youtube.com/feeds/videos.xml?channel_id=<platform_id>`` — no API key,
  no quota — for new video ids + published timestamps. Use ETag/Last-Modified +
  watermark for incremental polling.
- Enrichment (only for ids detection flags as new): YouTube Data API ``videos.list``
  (~1 quota unit) behind ``YOUTUBE_API_KEY`` for duration/tags. Never ``search.list``.

This stub registers the adapter so the type is visible and wiring is in place; ``poll``
raises until implemented. It stays disabled by default in config, so nothing runs it.
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


@register_source("youtube_channel")
class YouTubeChannelAdapter:
    tier: Tier = "A"

    def __init__(self, *, http=None, intel_config: IntelConfig | None = None) -> None:
        self._http = http
        self._config = intel_config

    def poll(self, source: IntelSource, state: SourceState, *, now: datetime) -> SourcePollResult:
        raise NotImplementedError(
            "YouTubeChannelAdapter is a Phase 3 stub. Implement feed-first detection "
            "(channel Atom feed) + Data-API enrich-on-new. See docs/ runbook §7 Phase 3."
        )
