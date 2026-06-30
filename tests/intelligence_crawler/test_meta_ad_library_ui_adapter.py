from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.meta_ad_library_probe import MetaProbeCard, MetaProbeResult
from ad_classifier.intelligence_crawler.models import IntelSource, SourceState
from ad_classifier.intelligence_crawler.sources.base import available_source_types
from ad_classifier.intelligence_crawler.sources.meta_ad_library_ui import (
    MetaAdLibraryUiAdapter,
    build_meta_ad_library_url,
)

NOW = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)


def _probe_result(**_kwargs) -> MetaProbeResult:
    return MetaProbeResult(
        source_url="https://www.facebook.com/ads/library/?view_all_page_id=7037526514",
        final_url="https://www.facebook.com/ads/library/?view_all_page_id=7037526514",
        fetched_at=NOW.isoformat(),
        cards_count=1,
        full_page_screenshot=None,
        cards=[
            MetaProbeCard(
                index=0,
                library_id="1500648444745170",
                status="active",
                started_running="Apr 21, 2026",
                platforms=["Facebook", "Instagram"],
                text=(
                    "Active Library ID: 1500648444745170 Started running on Apr 21, "
                    "2026 Jeep Sponsored Go all the way to the All-New Jeep Cherokee Hybrid"
                ),
                text_excerpt="Jeep Sponsored Go all the way",
                links=[{"text": "Jeep", "href": "https://www.facebook.com/Jeep/"}],
                image_sources=["https://example.test/creative.jpg"],
                video_sources=["blob:https://www.facebook.com/video"],
                video_posters=["https://example.test/poster.jpg"],
                background_image_sources=["https://example.test/background.jpg"],
                video_count=1,
                creative_variant_count=5,
                has_multiple_versions=True,
                screenshot_path="cache/card.png",
            )
        ],
    )


def test_meta_ad_library_ui_is_registered() -> None:
    assert "meta_ad_library_ui" in available_source_types()


def test_build_meta_ad_library_url_uses_page_id_and_active_status() -> None:
    url = build_meta_ad_library_url(
        "7037526514",
        active_status="active",
        sort_mode="total_impressions",
        sort_direction="desc",
    )
    params = parse_qs(urlparse(url).query)

    assert "view_all_page_id=7037526514" in url
    assert params["country"] == ["US"]
    assert params["active_status"] == ["active"]
    assert params["search_type"] == ["page"]
    assert params["sort_data[mode]"] == ["total_impressions"]
    assert params["sort_data[direction]"] == ["desc"]


def test_meta_adapter_converts_probe_cards_to_raw_source_items(tmp_path) -> None:
    adapter = MetaAdLibraryUiAdapter(
        intel_config=IntelConfig(cache_dir=tmp_path),
        probe_runner=_probe_result,
    )
    source = IntelSource(
        id="jeep_meta_ads",
        brand_name="Jeep",
        source_type="meta_ad_library_ui",
        tier="B",
        platform="meta",
        platform_id="7037526514",
        config={"active_status": "active", "scrolls": 2, "max_cards": 5},
    )

    result = adapter.poll(source, SourceState(source_id=source.id), now=NOW)

    assert result.errors == []
    assert len(result.items) == 1
    item = result.items[0]
    assert item.external_id == "1500648444745170"
    assert item.resource_type == "meta_ad"
    assert item.title == "Jeep Meta ad 1500648444745170"
    assert item.description == "Go all the way to the All-New Jeep Cherokee Hybrid"
    assert item.url == "https://www.facebook.com/ads/library/?id=1500648444745170"
    assert item.thumbnail_url == "https://example.test/creative.jpg"
    assert item.published_at == datetime(2026, 4, 21, tzinfo=UTC)
    assert item.raw["status"] == "active"
    assert item.raw["video_count"] == 1
    assert item.raw["creative_variant_count"] == 5
    assert item.raw["has_multiple_versions"] is True
    assert item.raw["video_sources"] == ["blob:https://www.facebook.com/video"]
    assert item.raw["video_posters"] == ["https://example.test/poster.jpg"]


def test_meta_adapter_requires_page_id(tmp_path) -> None:
    adapter = MetaAdLibraryUiAdapter(intel_config=IntelConfig(cache_dir=tmp_path))
    source = IntelSource(id="bad", brand_name="Jeep", source_type="meta_ad_library_ui")

    result = adapter.poll(source, SourceState(source_id=source.id), now=NOW)

    assert result.items == []
    assert "platform_id" in result.errors[0]


def test_meta_adapter_can_filter_statuses_locally(tmp_path) -> None:
    def probe_result(**_kwargs) -> MetaProbeResult:
        return MetaProbeResult(
            source_url="https://www.facebook.com/ads/library/?view_all_page_id=1",
            final_url="https://www.facebook.com/ads/library/?view_all_page_id=1",
            fetched_at=NOW.isoformat(),
            cards_count=2,
            full_page_screenshot=None,
            cards=[
                MetaProbeCard(
                    index=0,
                    library_id="111",
                    status="active",
                    started_running="Jun 1, 2026",
                    platforms=[],
                    text_excerpt="Active Library ID: 111",
                    text="Active Library ID: 111",
                ),
                MetaProbeCard(
                    index=1,
                    library_id="222",
                    status="inactive",
                    started_running="May 1, 2026",
                    platforms=[],
                    text_excerpt="Inactive Library ID: 222",
                    text="Inactive Library ID: 222",
                ),
            ],
        )

    adapter = MetaAdLibraryUiAdapter(
        intel_config=IntelConfig(cache_dir=tmp_path),
        probe_runner=probe_result,
    )
    source = IntelSource(
        id="toyota_meta_ads",
        brand_name="Toyota",
        source_type="meta_ad_library_ui",
        tier="B",
        platform="meta",
        platform_id="197052454200",
        config={"active_status": "all", "include_statuses": ["active"]},
    )

    result = adapter.poll(source, SourceState(source_id=source.id), now=NOW)

    assert result.errors == []
    assert [item.external_id for item in result.items] == ["111"]


def test_meta_adapter_passes_scroll_and_sort_config_to_probe(tmp_path) -> None:
    captured = {}

    def probe_result(**kwargs) -> MetaProbeResult:
        captured.update(kwargs)
        return MetaProbeResult(
            source_url=kwargs["url"],
            final_url=kwargs["url"],
            fetched_at=NOW.isoformat(),
            cards_count=0,
            full_page_screenshot=None,
            cards=[],
        )

    adapter = MetaAdLibraryUiAdapter(
        intel_config=IntelConfig(cache_dir=tmp_path),
        probe_runner=probe_result,
    )
    source = IntelSource(
        id="toyota_meta_ads",
        brand_name="Toyota",
        source_type="meta_ad_library_ui",
        tier="B",
        platform="meta",
        platform_id="197052454200",
        config={
            "active_status": "active",
            "sort_mode": "relevancy_monthly_grouped",
            "sort_direction": "desc",
            "scrolls": 18,
            "max_cards": 300,
            "wait_ms": 900,
            "stop_after_no_new": 4,
        },
    )

    result = adapter.poll(source, SourceState(source_id=source.id), now=NOW)
    params = parse_qs(urlparse(str(captured["url"])).query)

    assert result.errors == []
    assert params["active_status"] == ["active"]
    assert params["sort_data[mode]"] == ["relevancy_monthly_grouped"]
    assert captured["scrolls"] == 18
    assert captured["max_cards"] == 300
    assert captured["wait_ms"] == 900
    assert captured["stop_after_no_new"] == 4
