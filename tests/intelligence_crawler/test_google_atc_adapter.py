from __future__ import annotations

from datetime import UTC, datetime

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.google_atc_rpc import (
    US_REGION_CODE,
    advertiser_creatives_freq,
    lookup_advertiser,
    parse_creatives,
    parse_preview_artifacts,
    resolve_advertiser,
    search_advertisers,
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
    "5": 2,
}  # no field "2" -> single page (no continuation token)

PREVIEW_JS = r"""
fletchCallback({
  "html": "<a href=\"https:\/\/www.jeep.com\/wagoneer.html\">Jeep Wagoneer<\/a>
  <img src=\"https:\/\/cdn.example.com\/creative.webp\">
  <iframe src=\"https:\/\/www.youtube.com\/embed\/x5vcvScUoIM\"><\/iframe>
  <img src=\"https:\/\/i.ytimg.com\/vi\/x5vcvScUoIM\/hqdefault.jpg\">",
  "media": "https:\/\/rr1---sn.example.googlevideo.com\/videoplayback?id=o-A123&mime=video\/mp4"
})
"""


# Image/display creatives inline the ad HTML at field 3.3.2 (live Apple/Ford/Toyota/Nike shape):
# no 3.1.4 preview_url, format code 1, an <img> on the ad-image CDN.
INLINE_IMAGE_PAYLOAD = {
    "1": [
        {
            "1": ADV,
            "2": "CR_IMG_1",
            "3": {
                "3": {
                    "2": (
                        '<img src="https://tpc.googlesyndication.com/archive/simgad/12345"'
                        ' height="275" width="348">'
                    )
                },
                "5": True,
            },
            "4": 1,
            "6": {"1": "1774647000"},
            "12": "Apple Inc",
        }
    ]
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
    assert first.raw["preview_enriched"] is False
    assert first.raw["video_sources"] == []
    # watermark = latest first-shown across creatives
    assert result.new_watermark == datetime.fromtimestamp(1774647000, tz=UTC).isoformat()


def test_parse_preview_artifacts_extracts_video_and_image_assets():
    artifacts = parse_preview_artifacts(
        PREVIEW_JS,
        preview_url="https://displayads-formats.googleusercontent.com/ads/preview/content.js?x=1",
    )

    assert artifacts["youtube_video_ids"] == ["x5vcvScUoIM"]
    assert "https://www.youtube.com/watch?v=x5vcvScUoIM" in artifacts["video_sources"]
    assert any("googlevideo.com/videoplayback" in url for url in artifacts["video_sources"])
    assert "https://i.ytimg.com/vi/x5vcvScUoIM/hqdefault.jpg" in artifacts["video_posters"]
    assert "https://cdn.example.com/creative.webp" in artifacts["image_sources"]
    # We no longer scrape arbitrary URLs as "destinations" — a minified bundle is too noisy.
    assert "links" not in artifacts


def test_preview_artifacts_do_not_scrape_destination_links():
    # A minified preview bundle contains library/namespace URLs (amp runtime, safevalues issues,
    # w3.org/svg, …) that are NOT the ad's landing page. None of them may surface as artifacts.
    js = (
        'a("https:\\/\\/cdn.ampproject.org\\/amp4ads-host-v0.js");'
        'b("https:\\/\\/github.com\\/google\\/safevalues\\/issues");'
        'c("http:\\/\\/www.w3.org\\/2000\\/svg");'
        'd("https:\\/\\/www.jeep.com\\/wagoneer.html");'
    )
    # None are a YouTube id / video / image extension, so nothing is captured at all.
    assert parse_preview_artifacts(js) == {}


# A DV360/Studio rich-media bundle (live Ford shape): hex-escaped quotes, a BACKUP_IMAGE
# simgad URL with no file extension, a tracking pixel, and a double-escaped VAST
# <MediaFile> section whose URL previously came out corrupted (XML tail + "\=" residue).
STUDIO_PREVIEW_JS = (
    r"var p = {type: \x27IMAGE\x27,renderAs: \x27BACKUP_IMAGE\x27,width: \x27300\x27,"
    r"url: \x27https://s0.2mdn.net/simgad/1013946659373396495\x27};"
    r"i(\x22https://s0.2mdn.net/dot.gif]]\\x3e\\x3c/Impression\\x3e\x22);"
    r"v(\x22https://gcdn.2mdn.net/videoplayback?id\\x3d816cae\\x26mime\\x3dvideo/mp4]]"
    r"\\x3e\\x3c/MediaFile\\x3e\x22);"
)


def test_preview_artifacts_decode_escapes_capture_backup_image_and_clean_vast():
    artifacts = parse_preview_artifacts(STUDIO_PREVIEW_JS)
    # The extension-less BACKUP_IMAGE on the ad CDN is the rich-media creative's static form.
    assert artifacts["image_sources"] == ["https://s0.2mdn.net/simgad/1013946659373396495"]
    # The VAST video URL comes out clean: no XML tail, no escape residue.
    assert artifacts["video_sources"] == [
        "https://gcdn.2mdn.net/videoplayback?id=816cae&mime=video/mp4"
    ]
    # The impression pixel never surfaces as a creative artifact.
    assert not any("dot.gif" in url for url in artifacts["image_sources"])


def test_adapter_enriches_preview_artifacts_when_fetcher_is_available():
    preview_calls = []

    def preview_fetch(url):
        preview_calls.append(url)
        return PREVIEW_JS

    adapter = GoogleAtcAdapter(
        rpc_fetch=lambda m, q: SEARCH_PAYLOAD,
        preview_fetch=preview_fetch,
        intel_config=IntelConfig(),
    )
    result = adapter.poll(
        _source(config={"preview_enrichment_limit": 1}),
        SourceState(source_id="salesforce_atc"),
        now=NOW,
    )

    assert result.errors == []
    assert preview_calls == [
        "https://displayads-formats.googleusercontent.com/ads/preview/content.js?x=1"
    ]
    first = result.items[0]
    assert first.thumbnail_url == "https://i.ytimg.com/vi/x5vcvScUoIM/hqdefault.jpg"
    assert first.raw["preview_enriched"] is True
    assert first.raw["youtube_video_ids"] == ["x5vcvScUoIM"]
    assert "https://www.youtube.com/watch?v=x5vcvScUoIM" in first.raw["video_sources"]
    assert first.raw["image_sources"] == ["https://cdn.example.com/creative.webp"]
    assert result.items[1].raw["preview_enriched"] is False


def test_adapter_preview_enrichment_failure_keeps_items():
    def preview_fetch(url):
        raise RuntimeError("preview 403")

    adapter = GoogleAtcAdapter(
        rpc_fetch=lambda m, q: SEARCH_PAYLOAD,
        preview_fetch=preview_fetch,
        intel_config=IntelConfig(),
    )
    result = adapter.poll(_source(), SourceState(source_id="salesforce_atc"), now=NOW)

    assert [item.external_id for item in result.items] == [
        "CR17113391207746109441",
        "CR99988877766655544433",
    ]
    assert result.outcome == "partial"
    assert result.diagnostics[0].category == "asset_fetch"
    assert result.diagnostics[0].code == "google_preview_asset_fetch_failed"
    assert result.items[0].raw["preview_enriched"] is False


def test_pagination_follows_cursor_and_dedups():
    # page 1 carries a continuation token (field "2"); page 2 has none -> stop.
    page1 = {
        "1": [{"1": ADV, "2": "CR_A", "6": {"1": "1770000000"}}],
        "2": "TOKEN_ABC",
    }
    page2 = {"1": [{"1": ADV, "2": "CR_B", "6": {"1": "1771000000"}}]}
    calls = []

    def fetch(method, freq):
        calls.append(freq)
        return page1 if "4" not in freq else page2

    adapter = GoogleAtcAdapter(rpc_fetch=fetch, intel_config=IntelConfig())
    result = adapter.poll(
        _source(config={"max_pages": 5}), SourceState(source_id="salesforce_atc"), now=NOW
    )

    assert [i.external_id for i in result.items] == ["CR_A", "CR_B"]
    assert len(calls) == 2  # stopped after page 2 (no token)
    assert calls[1]["4"] == "TOKEN_ABC"  # page-2 request carried the cursor


def test_pagination_respects_max_pages():
    # every page returns a token AND new ids -> bounded by max_pages.
    def fetch(method, freq):
        n = freq.get("4", "0")
        nxt = str(int(n) + 1) if n != "0" else "1"
        return {"1": [{"1": ADV, "2": f"CR_{n}", "6": {"1": "1770000000"}}], "2": nxt}

    adapter = GoogleAtcAdapter(rpc_fetch=fetch, intel_config=IntelConfig())
    result = adapter.poll(
        _source(config={"max_pages": 3}), SourceState(source_id="salesforce_atc"), now=NOW
    )
    assert len(result.items) == 3  # exactly max_pages pages fetched
    assert result.outcome == "partial"
    assert result.truncated is True
    assert result.diagnostics[0].category == "request_limit"


def test_later_page_failure_retains_prior_pages_and_reports_partial():
    calls = 0

    def fetch(method, freq):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "1": [{"1": ADV, "2": "CR_A", "6": {"1": "1770000000"}}],
                "2": "TOKEN_ABC",
            }
        raise RuntimeError("rpc 429")

    adapter = GoogleAtcAdapter(rpc_fetch=fetch, intel_config=IntelConfig())
    result = adapter.poll(
        _source(config={"max_pages": 5}), SourceState(source_id="salesforce_atc"), now=NOW
    )

    assert [item.external_id for item in result.items] == ["CR_A"]
    assert result.outcome == "partial"
    assert result.complete is False
    assert result.diagnostics[0].category == "rate_limited"
    assert result.truncation_reason == "Google pagination was interrupted by a provider error."


def test_unlimited_pagination_stops_on_429_without_preview_requests():
    calls = 0
    preview_calls = 0

    def fetch(method, freq):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("rpc 429 too many requests")
        return {
            "1": [
                {
                    "1": ADV,
                    "2": f"CR_{calls}",
                    "3": {"1": {"4": f"https://preview/{calls}"}},
                    "6": {"1": "1770000000"},
                }
            ],
            "2": f"TOKEN_{calls}",
        }

    def preview_fetch(url):
        nonlocal preview_calls
        preview_calls += 1
        return PREVIEW_JS

    adapter = GoogleAtcAdapter(
        rpc_fetch=fetch,
        preview_fetch=preview_fetch,
        intel_config=IntelConfig(),
    )
    result = adapter.poll(
        _source(config={"max_pages": 0}), SourceState(source_id="salesforce_atc"), now=NOW
    )

    assert calls == 3
    assert preview_calls == 0
    assert [item.external_id for item in result.items] == ["CR_1", "CR_2"]
    assert result.outcome == "partial"
    assert result.diagnostics[0].category == "rate_limited"
    assert result.request_count == 3


def test_live_fetches_are_throttled_between_requests():
    # A poll may burst ~10 RPC pages + hundreds of preview GETs; Google answers bursts with
    # HTTP 429 (seen live). The adapter pauses between consecutive calls of each kind.
    slept: list[float] = []
    page1 = {
        "1": [{"1": ADV, "2": "CR_A", "3": {"1": {"4": "https://p/content.js?1"}}}],
        "2": "TOKEN",
    }
    page2 = {"1": [{"1": ADV, "2": "CR_B", "3": {"1": {"4": "https://p/content.js?2"}}}]}

    adapter = GoogleAtcAdapter(
        rpc_fetch=lambda m, q: page2 if "4" in q else page1,
        preview_fetch=lambda url: "no assets here",
        sleep=slept.append,
        intel_config=IntelConfig(),
    )
    adapter.poll(_source(), SourceState(source_id="salesforce_atc"), now=NOW)

    # One pause between the two RPC pages, one between the two preview fetches.
    assert slept == [0.75, 0.4]


def test_missing_advertiser_id_reports_error():
    adapter = GoogleAtcAdapter(rpc_fetch=lambda m, q: {}, intel_config=IntelConfig())
    result = adapter.poll(
        _source(platform_id=None), SourceState(source_id="salesforce_atc"), now=NOW
    )
    assert result.items == []
    assert result.outcome == "failed"
    assert result.diagnostics[0].code == "google_advertiser_id_missing"


def test_injected_feed_disables_network():
    # http injected (offline) + no rpc_fetch -> RPC client disabled, no live call.
    adapter = GoogleAtcAdapter(http=lambda *a, **k: None, intel_config=IntelConfig())
    result = adapter.poll(_source(), SourceState(source_id="salesforce_atc"), now=NOW)
    assert result.items == []
    assert result.outcome == "failed"
    assert result.diagnostics[0].code == "google_rpc_client_unavailable"


def test_rpc_failure_is_isolated():
    def boom(method, freq):
        raise RuntimeError("rpc 429")

    adapter = GoogleAtcAdapter(rpc_fetch=boom, intel_config=IntelConfig())
    result = adapter.poll(_source(), SourceState(source_id="salesforce_atc"), now=NOW)
    assert result.items == []
    assert result.outcome == "failed"
    assert result.diagnostics[0].category == "rate_limited"


def test_parse_creatives_extracts_inline_image_from_field_3_3_2():
    # The bug: parser only read 3.1.4 (preview_url) and missed the inline <img> at 3.3.2,
    # so image/display creatives (the common case for big brands) had no image.
    parsed = parse_creatives(INLINE_IMAGE_PAYLOAD)
    assert len(parsed) == 1
    creative = parsed[0]
    assert creative["image_sources"] == ["https://tpc.googlesyndication.com/archive/simgad/12345"]
    assert creative["image_url"] == "https://tpc.googlesyndication.com/archive/simgad/12345"
    assert creative["preview_url"] is None  # image creatives have no 3.1.4 hosted preview
    assert creative["format"] == "image"  # derived from content, not the numeric code (1 == "text")


def test_adapter_maps_inline_image_without_preview_fetch():
    # No preview_fetch injected, but the image is inline in the RPC -> still captured + rendered.
    adapter = GoogleAtcAdapter(
        rpc_fetch=lambda m, q: INLINE_IMAGE_PAYLOAD, intel_config=IntelConfig()
    )
    result = adapter.poll(_source(), SourceState(source_id="salesforce_atc"), now=NOW)

    item = result.items[0]
    assert item.raw["image_sources"] == ["https://tpc.googlesyndication.com/archive/simgad/12345"]
    assert item.thumbnail_url == "https://tpc.googlesyndication.com/archive/simgad/12345"
    assert item.raw["format"] == "image"
    assert item.raw["has_inline_image"] is True
    assert item.raw["preview_enriched"] is False  # no preview fetch needed for image creatives


def test_adapter_falls_back_to_brand_name_for_mojibake_advertiser_name():
    payload = {
        "1": [
            {
                "1": ADV,
                "2": "CR_MOJIBAKE",
                "3": {
                    "3": {"2": '<img src="https://tpc.googlesyndication.com/archive/simgad/12345">'}
                },
                "4": 1,
                "6": {"1": "1774647000"},
                "12": "McDONALD\ufffdS CORPORATION",
            }
        ]
    }
    adapter = GoogleAtcAdapter(rpc_fetch=lambda m, q: payload, intel_config=IntelConfig())
    source = _source(brand_name="McDonald's")

    item = adapter.poll(source, SourceState(source_id=source.id), now=NOW).items[0]

    assert item.title == "McDonald's ATC creative CR_MOJIBAKE"
    assert item.raw["advertiser_name"] == "McDonald's"
    assert item.raw["advertiser_name_raw"] == "McDONALD\ufffdS CORPORATION"


def test_hosted_creative_with_no_static_assets_is_marked_dynamic():
    # A format-2 hosted banner whose preview is pure JS (no youtube/image) is a server-rendered
    # rich-media creative — flag it and relabel it so the UI doesn't call it a missing "image".
    payload = {
        "1": [
            {
                "1": ADV,
                "2": "CR_DYN",
                "3": {
                    "1": {
                        "4": "https://displayads-formats.googleusercontent.com/ads/preview/content.js?d=1"
                    }
                },
                "4": 2,  # numeric map calls this "image"
                "6": {"1": "1774647000"},
                "12": "Apple Inc",
            }
        ]
    }
    adapter = GoogleAtcAdapter(
        rpc_fetch=lambda m, q: payload,
        preview_fetch=lambda url: "fletchCallback({var x=Object.create(null);})",  # no assets
        intel_config=IntelConfig(),
    )
    result = adapter.poll(_source(), SourceState(source_id="salesforce_atc"), now=NOW)

    item = result.items[0]
    assert item.raw["dynamic_creative"] is True
    assert item.raw["format"] == "rich_media"  # not the misleading "image"
    assert item.raw["image_sources"] == []
    assert item.raw["video_sources"] == []


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


# --- resolver -------------------------------------------------------------------------

# SearchSuggestions shape: official brand first, then dealers/namesakes/foreign.
SUGGEST_TOYOTA = {
    "1": [
        {"1": {"1": "Toyota", "2": "AR_TOYOTA", "3": "US"}},
        {"1": {"1": "Toyota GB", "2": "AR_TOYOTA_GB", "3": "GB"}},
        {"1": {"1": "Cox Toyota", "2": "AR_COX", "3": "US"}},
    ]
}
# A bare "Ford" query returns only dealers/namesakes (no exact "Ford").
SUGGEST_FORD_DEALERS = {
    "1": [
        {"1": {"1": "G Ford", "2": "AR_GFORD", "3": "US"}},
        {"1": {"1": "Ian Ford", "2": "AR_IAN", "3": "US"}},
    ]
}
# The legal-name query surfaces the real entity.
SUGGEST_FORD_LEGAL = {"1": [{"1": {"1": "Ford Motor Company", "2": "AR_FMC", "3": "US"}}]}


def test_search_advertisers_parses_suggestions():
    rows = search_advertisers("Toyota", fetch=lambda m, q: SUGGEST_TOYOTA)
    assert {"name": "Toyota", "advertiser_id": "AR_TOYOTA", "region": "US"} in rows
    assert len(rows) == 3


def test_resolve_advertiser_exact_us_match():
    chosen = resolve_advertiser("Toyota", fetch=lambda m, q: SUGGEST_TOYOTA)
    assert chosen is not None
    assert chosen["advertiser_id"] == "AR_TOYOTA"  # not the GB or dealer entries


def test_resolve_advertiser_refuses_to_guess():
    # Bare "Ford" returns only dealers/namesakes -> no exact match -> None (never a dealer).
    assert resolve_advertiser("Ford", fetch=lambda m, q: SUGGEST_FORD_DEALERS) is None


def test_resolve_advertiser_uses_legal_name_hints():
    def fetch(method, freq):
        return SUGGEST_FORD_LEGAL if freq["1"] == "Ford Motor Company" else SUGGEST_FORD_DEALERS

    chosen = resolve_advertiser(
        "Ford",
        fetch=fetch,
        accept_names=("Ford Motor Company",),
        extra_queries=("Ford Motor Company",),
    )
    assert chosen is not None and chosen["advertiser_id"] == "AR_FMC"
