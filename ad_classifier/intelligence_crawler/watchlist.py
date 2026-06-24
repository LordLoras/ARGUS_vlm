"""Build the US brand watchlist = entity-graph brands (read-only) ∪ YAML seed list.

The entity graph is opened strictly read-only. A brand is considered ready to poll only
once it has at least one enabled, US-pinned source (``has_verified_source``); graph
brands without a source are surfaced for source bootstrapping, never blind-scraped.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import structlog

from ad_classifier.entity_graph.utils import normalize_name
from ad_classifier.intelligence_crawler.config import IntelConfig
from ad_classifier.intelligence_crawler.models import WatchedBrand

logger = structlog.get_logger(__name__)


def build_watchlist(config: IntelConfig) -> list[WatchedBrand]:
    verified = _verified_brand_keys(config)
    brands: dict[str, WatchedBrand] = {}

    for name in config.watchlist.seed_brands:
        key = normalize_name(name)
        if not key:
            continue
        brands[key] = WatchedBrand(
            brand_name=name,
            normalized_name=key,
            origin="seed",
            has_verified_source=key in verified,
        )

    if config.watchlist.include_graph_brands:
        for node_id, name in _graph_brands(config.watchlist.entity_graph_db_path):
            key = normalize_name(name)
            if not key:
                continue
            existing = brands.get(key)
            if existing is not None:
                brands[key] = existing.model_copy(
                    update={"origin": "both", "graph_node_id": node_id}
                )
            else:
                brands[key] = WatchedBrand(
                    brand_name=name,
                    normalized_name=key,
                    origin="graph",
                    graph_node_id=node_id,
                    has_verified_source=key in verified,
                )

    return sorted(brands.values(), key=lambda brand: brand.normalized_name)


def _verified_brand_keys(config: IntelConfig) -> set[str]:
    return {
        normalize_name(source.brand)
        for source in config.sources
        if source.enabled and source.market == "US"
    }


def _graph_brands(path: Path | None) -> list[tuple[str, str]]:
    if path is None or not Path(path).exists():
        return []
    try:
        uri = Path(path).expanduser().resolve().as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        try:
            rows = conn.execute(
                "SELECT id, canonical_name FROM entity_nodes "
                "WHERE type = 'brand' AND status <> 'rejected'"
            ).fetchall()
            return [(str(row["id"]), str(row["canonical_name"])) for row in rows]
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.warning("watchlist_graph_read_failed", path=str(path), error=str(exc))
        return []
