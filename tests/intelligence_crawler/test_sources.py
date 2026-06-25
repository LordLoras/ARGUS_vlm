from __future__ import annotations

from ad_classifier.intelligence_crawler.config import IntelConfig, WatchlistConfig
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
