from __future__ import annotations

from datetime import UTC, datetime

from ad_classifier.intelligence_crawler.config import SourceConfig
from ad_classifier.intelligence_crawler.models import SourceState
from ad_classifier.intelligence_crawler.sources.youtube import (
    FeedResponse,
    YouTubeChannelAdapter,
    _duration_to_ms,
)

NOW = datetime(2026, 6, 24, tzinfo=UTC)

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Toyota USA</title>
  <entry>
    <id>yt:video:VID1</id>
    <yt:videoId>VID1</yt:videoId>
    <title>Camry Reborn | Toyota</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=VID1"/>
    <published>2026-06-20T15:00:00+00:00</published>
    <media:group>
      <media:description>The all-new Camry campaign.</media:description>
      <media:thumbnail url="https://i.ytimg.com/vi/VID1/hq.jpg"/>
    </media:group>
  </entry>
  <entry>
    <id>yt:video:VID2</id>
    <yt:videoId>VID2</yt:videoId>
    <title>Tacoma Trail | Toyota</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=VID2"/>
    <published>2026-06-19T10:00:00+00:00</published>
    <media:group>
      <media:description>Tacoma spot.</media:description>
    </media:group>
  </entry>
</feed>
"""


def _source():
    return SourceConfig(
        id="yt1",
        brand="Toyota",
        source_type="youtube_channel",
        tier="A",
        platform="youtube",
        platform_id="UC_TOYOTA_USA",
    ).to_source()


def test_parses_channel_feed():
    captured: dict = {}

    def fetch(url, headers):
        captured["url"] = url
        captured["headers"] = headers
        return FeedResponse(status_code=200, body=ATOM, etag='W/"abc"')

    adapter = YouTubeChannelAdapter(http=fetch)
    result = adapter.poll(_source(), SourceState(source_id="yt1"), now=NOW)

    assert "channel_id=UC_TOYOTA_USA" in captured["url"]
    ids = [i.external_id for i in result.items]
    assert ids == ["VID1", "VID2"]
    first = result.items[0]
    assert first.resource_type == "video"
    assert first.title == "Camry Reborn | Toyota"
    assert first.url == "https://www.youtube.com/watch?v=VID1"
    assert first.thumbnail_url == "https://i.ytimg.com/vi/VID1/hq.jpg"
    assert first.published_at == datetime(2026, 6, 20, 15, 0, tzinfo=UTC)
    # watermark = latest published; etag echoed for the next conditional poll.
    assert result.new_watermark == "2026-06-20T15:00:00+00:00"
    assert result.etag == 'W/"abc"'


def test_conditional_headers_and_304_yield_no_items():
    sent: dict = {}

    def fetch(url, headers):
        sent.update(headers)
        return FeedResponse(status_code=304, body="")

    state = SourceState(
        source_id="yt1",
        etag='W/"abc"',
        last_modified="Mon, 23 Jun 2026 00:00:00 GMT",
        watermark="2026-06-20T15:00:00+00:00",
    )
    result = YouTubeChannelAdapter(http=fetch).poll(_source(), state, now=NOW)

    assert sent["If-None-Match"] == 'W/"abc"'
    assert result.items == []
    assert result.new_watermark == "2026-06-20T15:00:00+00:00"  # preserved


def test_missing_channel_id_reports_error():
    source = SourceConfig(
        id="yt1", brand="Toyota", source_type="youtube_channel", tier="A"
    ).to_source()
    result = YouTubeChannelAdapter(http=lambda u, h: FeedResponse(200, ATOM)).poll(
        source, SourceState(source_id="yt1"), now=NOW
    )
    assert result.items == []
    assert result.errors and "platform_id" in result.errors[0]


def test_injected_feed_does_not_enrich_durations():
    # No json_http injected + an injected feed fetcher → enrichment disabled (no network),
    # so feed items carry no duration regardless of any real key on the machine.
    result = YouTubeChannelAdapter(http=lambda u, h: FeedResponse(200, ATOM, etag=None)).poll(
        _source(), SourceState(source_id="yt1"), now=NOW
    )
    assert [i.duration_ms for i in result.items] == [None, None]


def test_enriches_durations_via_videos_list():
    captured: dict = {}

    def json_fetch(url):
        captured["url"] = url
        return {
            "items": [
                {"id": "VID1", "contentDetails": {"duration": "PT1M35S"}},  # 95s
                {"id": "VID2", "contentDetails": {"duration": "PT12M4S"}},  # long-form
            ]
        }

    adapter = YouTubeChannelAdapter(
        http=lambda u, h: FeedResponse(200, ATOM),
        json_http=json_fetch,
        api_key="TESTKEY",
    )
    result = adapter.poll(_source(), SourceState(source_id="yt1"), now=NOW)

    by_id = {i.external_id: i for i in result.items}
    assert by_id["VID1"].duration_ms == 95_000
    assert by_id["VID2"].duration_ms == 724_000
    # videos.list query is well-formed: contentDetails part, both ids batched, key present.
    assert "part=contentDetails" in captured["url"]
    assert "id=VID1,VID2" in captured["url"]
    assert "key=TESTKEY" in captured["url"]


def test_enrichment_skipped_without_key():
    calls: list[str] = []

    def json_fetch(url):
        calls.append(url)
        return {"items": []}

    # Point the source at an env var that is guaranteed unset, so no key resolves and
    # enrichment is a no-op even on a machine that holds a real YOUTUBE_API_KEY.
    source = SourceConfig(
        id="yt1",
        brand="Toyota",
        source_type="youtube_channel",
        tier="A",
        platform="youtube",
        platform_id="UC_TOYOTA_USA",
        config={"api_key_env": "DEFINITELY_UNSET_INTEL_TEST_KEY"},
    ).to_source()
    adapter = YouTubeChannelAdapter(http=lambda u, h: FeedResponse(200, ATOM), json_http=json_fetch)
    result = adapter.poll(source, SourceState(source_id="yt1"), now=NOW)

    assert calls == []  # never hit the Data API
    assert all(i.duration_ms is None for i in result.items)


def test_enrichment_failure_is_isolated():
    def json_fetch(url):
        raise RuntimeError("quota exceeded")

    adapter = YouTubeChannelAdapter(
        http=lambda u, h: FeedResponse(200, ATOM),
        json_http=json_fetch,
        api_key="TESTKEY",
    )
    result = adapter.poll(_source(), SourceState(source_id="yt1"), now=NOW)

    # The poll still succeeds with feed items; durations just stay unset.
    assert [i.external_id for i in result.items] == ["VID1", "VID2"]
    assert all(i.duration_ms is None for i in result.items)


def test_duration_to_ms_parsing():
    assert _duration_to_ms("PT1M35S") == 95_000
    assert _duration_to_ms("PT45S") == 45_000
    assert _duration_to_ms("PT1H2M3S") == 3_723_000
    assert _duration_to_ms("PT0S") == 0
    assert _duration_to_ms("P0D") is None  # live/no-time-component → unparseable
    assert _duration_to_ms("garbage") is None
