from __future__ import annotations

from ad_classifier.intelligence_crawler.config import IntelConfig, SourceConfig, WatchlistConfig
from ad_classifier.intelligence_crawler.manager import IntelManager
from ad_classifier.intelligence_crawler.models import IntelSource


def _manager(tmp_path) -> IntelManager:
    config = IntelConfig(
        db_path=tmp_path / "intel.db",
        watchlist=WatchlistConfig(
            include_graph_brands=False, entity_graph_db_path=None, seed_brands=[]
        ),
        sources=[],  # nothing in YAML — everything comes from the DB registry
    )
    return IntelManager(config)


def test_source_crud_via_manager(tmp_path):
    manager = _manager(tmp_path)
    manager.upsert_source(
        IntelSource(id="toy_rss", brand_name="Toyota", source_type="rss", tier="A", enabled=True)
    )
    manager.upsert_source(
        IntelSource(id="ford_rss", brand_name="Ford", source_type="rss", tier="B", enabled=False)
    )

    assert {s.id for s in manager.list_sources()} == {"toy_rss", "ford_rss"}
    assert {s.id for s in manager.list_sources(enabled_only=True)} == {"toy_rss"}
    assert {s.id for s in manager.list_sources(brand="Toyota")} == {"toy_rss"}

    manager.set_source_enabled("ford_rss", True)
    assert {s.id for s in manager.list_sources(enabled_only=True)} == {"toy_rss", "ford_rss"}

    assert manager.delete_source("ford_rss") is True
    assert {s.id for s in manager.list_sources()} == {"toy_rss"}
    assert manager.delete_source("missing") is False


def test_config_sources_seed_db_on_manager_startup(tmp_path):
    config = IntelConfig(
        db_path=tmp_path / "intel.db",
        watchlist=WatchlistConfig(
            include_graph_brands=False,
            entity_graph_db_path=None,
            seed_brands=["Toyota", "Jeep"],
        ),
        sources=[
            SourceConfig(
                id="toyota_meta_ads",
                brand="Toyota",
                source_type="meta_ad_library_ui",
                tier="B",
                platform="meta",
                platform_id="197052454200",
                enabled=False,
            ),
            SourceConfig(
                id="jeep_atc",
                brand="Jeep",
                source_type="google_atc",
                tier="B",
                platform="google",
                platform_id="AR18054808035703914497",
                enabled=False,
            ),
        ],
    )

    manager = IntelManager(config)

    assert {source.id for source in manager.list_sources()} == {"toyota_meta_ads", "jeep_atc"}
    overviews = {brand.brand_name: brand for brand in manager.list_brand_overviews()}
    assert overviews["Toyota"].source_count == 1
    assert overviews["Jeep"].source_types == ["google_atc"]


def test_config_seed_does_not_clobber_enabled_db_source(tmp_path):
    config = IntelConfig(
        db_path=tmp_path / "intel.db",
        watchlist=WatchlistConfig(
            include_graph_brands=False,
            entity_graph_db_path=None,
            seed_brands=["Toyota"],
        ),
        sources=[
            SourceConfig(
                id="toyota_meta_ads",
                brand="Toyota",
                source_type="meta_ad_library_ui",
                tier="B",
                platform="meta",
                platform_id="197052454200",
                enabled=False,
            )
        ],
    )
    manager = IntelManager(config)
    manager.set_source_enabled("toyota_meta_ads", True)

    # Constructing another manager from the same disabled YAML seed must not undo the
    # user's persisted Watcher toggle.
    manager = IntelManager(config)

    source = manager.get_source("toyota_meta_ads")
    assert source is not None
    assert source.enabled is True


def test_db_added_source_is_selected_and_crawled(tmp_path):
    """A source added to the DB (not present in YAML config) is crawled — proving the
    registry, not the YAML, is the source of truth."""
    manager = _manager(tmp_path)
    manager.upsert_source(
        IntelSource(
            id="m1",
            brand_name="Toyota",
            source_type="mock",
            tier="A",
            enabled=True,
            config={
                "items": [
                    {
                        "external_id": "v1",
                        "url": "https://yt/v1",
                        "resource_type": "video",
                        "title": "Camry spot",
                        "published_at": "2026-05-01T00:00:00+00:00",
                    }
                ]
            },
        )
    )

    summary = manager.run_crawl(due=True)
    assert summary.source_count == 1
    assert summary.items[0].source_id == "m1"
    assert summary.items[0].baseline is True  # first poll → baseline, records the catalogue


def test_disabled_source_is_not_crawled(tmp_path):
    manager = _manager(tmp_path)
    manager.upsert_source(
        IntelSource(id="m2", brand_name="Toyota", source_type="mock", tier="A", enabled=False)
    )
    summary = manager.run_crawl(due=True)
    assert summary.source_count == 0  # disabled → not selected

    # …but an explicit source_id runs it even when disabled.
    explicit = manager.run_crawl(source_id="m2")
    assert explicit.source_count == 1
