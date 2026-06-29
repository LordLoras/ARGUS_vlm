from __future__ import annotations

from datetime import UTC, datetime

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
                video_count=1,
                screenshot_path="cache/card.png",
            )
        ],
    )


def test_meta_ad_library_ui_is_registered() -> None:
    assert "meta_ad_library_ui" in available_source_types()


def test_build_meta_ad_library_url_uses_page_id_and_active_status() -> None:
    url = build_meta_ad_library_url("7037526514", active_status="all")

    assert "view_all_page_id=7037526514" in url
    assert "country=US" in url
    assert "active_status=all" in url
    assert "search_type=page" in url


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
        config={"active_status": "all", "scrolls": 2, "max_cards": 5},
    )

    result = adapter.poll(source, SourceState(source_id=source.id), now=NOW)

    assert result.errors == []
    assert len(result.items) == 1
    item = result.items[0]
    assert item.external_id == "1500648444745170"
    assert item.resource_type == "meta_ad"
    assert item.url == "https://www.facebook.com/ads/library/?id=1500648444745170"
    assert item.thumbnail_url == "https://example.test/creative.jpg"
    assert item.published_at == datetime(2026, 4, 21, tzinfo=UTC)
    assert item.raw["status"] == "active"
    assert item.raw["video_count"] == 1


def test_meta_adapter_requires_page_id(tmp_path) -> None:
    adapter = MetaAdLibraryUiAdapter(intel_config=IntelConfig(cache_dir=tmp_path))
    source = IntelSource(id="bad", brand_name="Jeep", source_type="meta_ad_library_ui")

    result = adapter.poll(source, SourceState(source_id=source.id), now=NOW)

    assert result.items == []
    assert "platform_id" in result.errors[0]
