from __future__ import annotations

from datetime import UTC, datetime

from ad_classifier.intelligence_crawler.config import SourceConfig
from ad_classifier.intelligence_crawler.models import SourceState
from ad_classifier.intelligence_crawler.sources.http import HttpResponse
from ad_classifier.intelligence_crawler.sources.rss import RssAdapter

NOW = datetime(2026, 6, 24, tzinfo=UTC)

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<title>Toyota Newsroom</title>
<item>
  <title>Camry Reborn campaign launches</title>
  <link>https://pressroom.toyota.com/camry-reborn</link>
  <guid>tag:toyota:camry-reborn</guid>
  <description>New campaign.</description>
  <pubDate>Sat, 20 Jun 2026 15:00:00 +0000</pubDate>
</item>
<item>
  <title>Tacoma news</title>
  <link>https://pressroom.toyota.com/tacoma</link>
  <description>Tacoma.</description>
  <pubDate>Fri, 19 Jun 2026 10:00:00 +0000</pubDate>
</item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<title>Brand</title>
<entry>
  <id>urn:1</id>
  <title>Spot launch</title>
  <link rel="alternate" href="https://brand.com/1"/>
  <published>2026-06-21T00:00:00+00:00</published>
  <summary>Body</summary>
</entry>
</feed>"""


def _source(url: str | None = "https://pressroom.toyota.com/feed"):
    return SourceConfig(id="rss1", brand="Toyota", source_type="rss", tier="B", url=url).to_source()


def _adapter(body: str, status: int = 200, etag: str | None = None):
    return RssAdapter(http=lambda _u, _h: HttpResponse(status, body, etag=etag))


def test_parses_rss_items():
    result = _adapter(RSS, etag='"e1"').poll(_source(), SourceState(source_id="rss1"), now=NOW)
    first = result.items[0]
    assert first.external_id == "tag:toyota:camry-reborn"
    assert first.url == "https://pressroom.toyota.com/camry-reborn"
    assert first.resource_type == "press"
    assert first.published_at == datetime(2026, 6, 20, 15, 0, tzinfo=UTC)
    # second item has no guid -> external_id falls back to the link
    assert result.items[1].external_id == "https://pressroom.toyota.com/tacoma"
    assert result.new_watermark == "2026-06-20T15:00:00+00:00"
    assert result.etag == '"e1"'


def test_parses_atom_items():
    result = _adapter(ATOM).poll(_source(), SourceState(source_id="rss1"), now=NOW)
    assert [i.external_id for i in result.items] == ["urn:1"]
    assert result.items[0].url == "https://brand.com/1"
    assert result.items[0].published_at == datetime(2026, 6, 21, 0, 0, tzinfo=UTC)


def test_304_preserves_watermark():
    state = SourceState(source_id="rss1", etag='"e1"', watermark="2026-06-20T15:00:00+00:00")
    result = _adapter("", status=304).poll(_source(), state, now=NOW)
    assert result.items == []
    assert result.new_watermark == "2026-06-20T15:00:00+00:00"


def test_missing_url_reports_error():
    result = _adapter(RSS).poll(_source(url=None), SourceState(source_id="rss1"), now=NOW)
    assert result.items == []
    assert result.outcome == "failed"
    assert result.diagnostics[0].code == "rss_feed_url_missing"


def test_malformed_feed_is_failure_not_empty_success():
    result = _adapter("<html>not a feed</html>").poll(
        _source(), SourceState(source_id="rss1"), now=NOW
    )
    assert result.outcome == "failed"
    assert result.diagnostics[0].category == "parse_error"
