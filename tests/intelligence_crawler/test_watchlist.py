from __future__ import annotations

from ad_classifier.intelligence_crawler.config import IntelConfig, SourceConfig, WatchlistConfig
from ad_classifier.intelligence_crawler.watchlist import build_watchlist


def _config(tmp_path):
    return IntelConfig(
        db_path=tmp_path / "intel.db",
        watchlist=WatchlistConfig(
            include_graph_brands=False, entity_graph_db_path=None, seed_brands=["Toyota", "Ford"]
        ),
        sources=[
            SourceConfig(id="s1", brand="Toyota", source_type="mock", tier="A", enabled=True),
        ],
    )


def test_seed_brands_and_verified_source_flag(tmp_path):
    watchlist = build_watchlist(_config(tmp_path))
    by_key = {b.normalized_name: b for b in watchlist}
    assert {"toyota", "ford"} <= set(by_key)
    # Toyota has an enabled US source; Ford does not.
    assert by_key["toyota"].has_verified_source is True
    assert by_key["ford"].has_verified_source is False
    assert by_key["toyota"].origin == "seed"
