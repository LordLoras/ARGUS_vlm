from __future__ import annotations

from datetime import UTC, datetime

from ad_classifier.intelligence_crawler.models import IntelResource, RawSourceItem
from ad_classifier.intelligence_crawler.repository import IntelRepository
from ad_classifier.intelligence_crawler.runner import IntelRunner
from ad_classifier.intelligence_crawler.schema import initialize_intelligence_crawler_db

NOW = datetime(2026, 6, 30, tzinfo=UTC)


def _repo(tmp_path) -> IntelRepository:
    db = tmp_path / "intel.db"
    initialize_intelligence_crawler_db(db)
    return IntelRepository(db)


def test_migration_idempotent_and_adds_columns(tmp_path) -> None:
    db = tmp_path / "intel.db"
    first = initialize_intelligence_crawler_db(db)
    assert "002_resource_variants" in first
    # second init applies nothing new
    assert initialize_intelligence_crawler_db(db) == []
    import sqlite3

    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(intel_resources)")}
    assert {"variant_count", "has_variants"} <= cols


def test_resource_variant_columns_round_trip(tmp_path) -> None:
    repo = _repo(tmp_path)
    with repo.connect() as conn:
        repo.sync_sources(conn, [_src()])
        conn.commit()
        repo.insert_resource(
            conn,
            IntelResource(
                id="r1",
                source_id="s1",
                resource_type="meta_ad",
                first_seen_at=NOW,
                fetched_at=NOW,
                variant_count=5,
                has_variants=True,
            ),
        )
        conn.commit()
        views = repo.list_resources(conn, source_id="s1")
    assert len(views) == 1
    assert views[0].variant_count == 5
    assert views[0].has_variants is True


def test_runner_build_resource_maps_variants_from_raw() -> None:
    runner = IntelRunner.__new__(IntelRunner)  # no DB needed for _build_resource

    class _Decision:
        kind = "live"
        resource_id = "rid"
        item = RawSourceItem(
            external_id="lib1",
            url="https://example.test/ad",
            resource_type="meta_ad",
            raw={"creative_variant_count": 7, "has_multiple_versions": True},
        )

    res = runner._build_resource(_Decision(), _src(), "run1", NOW)
    assert res.variant_count == 7
    assert res.has_variants is True


def test_runner_build_resource_defaults_no_variants() -> None:
    runner = IntelRunner.__new__(IntelRunner)

    class _Decision:
        kind = "live"
        resource_id = "rid"
        item = RawSourceItem(external_id="x", url="https://e.test", resource_type="atc_ad", raw={})

    res = runner._build_resource(_Decision(), _src(), "run1", NOW)
    assert res.variant_count is None
    assert res.has_variants is False


def _src():
    from ad_classifier.intelligence_crawler.models import IntelSource

    return IntelSource(
        id="s1", brand_name="Jeep", source_type="meta_ad_library_ui", tier="B", platform="meta"
    )
