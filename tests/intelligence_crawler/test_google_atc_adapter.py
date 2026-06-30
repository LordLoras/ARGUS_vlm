from __future__ import annotations

from datetime import UTC, datetime

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.google_atc_rpc import (
    US_REGION_CODE,
    advertiser_creatives_freq,
    lookup_advertiser,
    parse_creatives,
)
from ad_classifier.intelligence_crawler.models import IntelSource, SourceState
from ad_classifier.intelligence_crawler.sources.base import available_source_types
from ad_classifier.intelligence_crawler.sources.google_atc import GoogleAtcAdapter

NOW = datetime(2026, 6, 30, tzinfo=UTC)
ADV = "AR03692565387905335297"

# Shape captured live from SearchService/SearchCreatives (Salesforce advertiser).
SEARCH_PAYLOAD = {
    "1": [
        {
            "1": ADV,
            "2": "CR17113391207746109441",
            "3": {
                "1": {
                    "4": "https://displayads-formats.googleusercontent.com/ads/preview/content.js?x=1"
                }
            },
            "4": 3,
            "6": {"1": "1774647000"},
            "7": {"1": "1778248800"},
            "12": "Salesforce, Inc.",
            "13": 38,
            "16": True,
        },
        {
            "1": ADV,
            "2": "CR99988877766655544433",
            "4": 2,
            "6": {"1": "1770000000"},
            "12": "Salesforce, Inc.",
        },
    ],
    "2": "next_cursor",
    "5": 2,
}


def _source(**overrides):
    base = dict(
        id="salesforce_atc",
        brand_name="Salesforce",
        source_type="google_atc",
        tier="B",
        platform="google",
        platform_id=ADV,
    )
    base.update(overrides)
    return IntelSource(**base)


def test_google_atc_is_registered():
    assert "google_atc" in available_source_types()


def test_request_uses_us_region_and_advertiser_filter():
    captured = {}

    def fetch(service_method, f_req):
        captured["method"] = service_method
        captured["f_req"] = f_req
        return SEARCH_PAYLOAD

    adapter = GoogleAtcAdapter(rpc_fetch=fetch, intel_config=IntelConfig())
    adapter.poll(
        _source(config={"page_size": 25}), SourceState(source_id="salesforce_atc"), now=NOW
    )

    assert captured["method"] == "SearchService/SearchCreatives"
    f = captured["f_req"]
    assert f["2"] == 25  # page size
    assert f["3"]["8"] == [US_REGION_CODE]  # US-only
    assert f["3"]["13"]["1"] == [ADV]  # advertiser-anchored


def test_creatives_map_to_items():
    adapter = GoogleAtcAdapter(rpc_fetch=lambda m, q: SEARCH_PAYLOAD, intel_config=IntelConfig())
    result = adapter.poll(_source(), SourceState(source_id="salesforce_atc"), now=NOW)

    assert result.errors == []
    assert [i.external_id for i in result.items] == [
        "CR17113391207746109441",
        "CR99988877766655544433",
    ]
    first = result.items[0]
    assert first.resource_type == "atc_ad"
    assert first.url == (
        f"https://adstransparency.google.com/advertiser/{ADV}"
        "/creative/CR17113391207746109441?region=US"
    )
    assert first.title == "Salesforce, Inc. ATC creative CR17113391207746109441"
    assert first.published_at == datetime.fromtimestamp(1774647000, tz=UTC)
    assert first.raw["format"] == "video"  # format code 3
    assert first.raw["last_shown"] == 1778248800
    assert first.raw["region"] == "US"
    assert first.raw["advertiser_name"] == "Salesforce, Inc."
    assert "content.js" in first.raw["preview_url"]
    # watermark = latest first-shown across creatives
    assert result.new_watermark == datetime.fromtimestamp(1774647000, tz=UTC).isoformat()


def test_missing_advertiser_id_reports_error():
    adapter = GoogleAtcAdapter(rpc_fetch=lambda m, q: {}, intel_config=IntelConfig())
    result = adapter.poll(
        _source(platform_id=None), SourceState(source_id="salesforce_atc"), now=NOW
    )
    assert result.items == []
    assert result.errors and "platform_id" in result.errors[0]


def test_injected_feed_disables_network():
    # http injected (offline) + no rpc_fetch -> RPC client disabled, no live call.
    adapter = GoogleAtcAdapter(http=lambda *a, **k: None, intel_config=IntelConfig())
    result = adapter.poll(_source(), SourceState(source_id="salesforce_atc"), now=NOW)
    assert result.items == []
    assert result.errors and "rpc client" in result.errors[0]


def test_rpc_failure_is_isolated():
    def boom(method, freq):
        raise RuntimeError("rpc 429")

    adapter = GoogleAtcAdapter(rpc_fetch=boom, intel_config=IntelConfig())
    result = adapter.poll(_source(), SourceState(source_id="salesforce_atc"), now=NOW)
    assert result.items == []
    assert result.errors and "rpc 429" in result.errors[0]


def test_parse_creatives_helper_skips_invalid():
    parsed = parse_creatives({"1": [{"2": "CRok", "1": "ARx"}, {"no_id": True}, "garbage"]})
    assert [c["creative_id"] for c in parsed] == ["CRok"]


def test_advertiser_creatives_freq_shape():
    freq = advertiser_creatives_freq("ARtest", region=US_REGION_CODE, page_size=40)
    assert freq["2"] == 40
    assert freq["3"]["8"] == [2840]
    assert freq["3"]["13"]["1"] == ["ARtest"]


def test_lookup_advertiser_parse():
    payload = {"1": {"1": "ARx", "2": "Expedia Inc", "11": "US"}}
    info = lookup_advertiser("ARx", fetch=lambda m, q: payload)
    assert info == {"advertiser_id": "ARx", "name": "Expedia Inc", "region": "US"}
