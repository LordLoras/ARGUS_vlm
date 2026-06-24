from __future__ import annotations

from datetime import UTC, datetime

from ad_classifier.intelligence_crawler.config import SourceConfig
from ad_classifier.intelligence_crawler.models import SourceState
from ad_classifier.intelligence_crawler.sources.youtube import FeedResponse, YouTubeChannelAdapter

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
