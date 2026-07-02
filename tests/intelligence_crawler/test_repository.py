from __future__ import annotations

from datetime import UTC, datetime

from ad_classifier.intelligence_crawler.config import SourceConfig
from ad_classifier.intelligence_crawler.models import IntelResource, IntelSignal
from ad_classifier.intelligence_crawler.repository import IntelRepository

NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def _repo_with_source(tmp_path):
    repo = IntelRepository(tmp_path / "intel.db")
    source = SourceConfig(id="s1", brand="Toyota", source_type="mock", tier="A").to_source()
    with repo.connect() as conn:
        repo.sync_sources(conn, [source])
        conn.commit()
    return repo


def test_resource_insert_is_idempotent(tmp_path):
    repo = _repo_with_source(tmp_path)
    res = IntelResource(
        id="res1", source_id="s1", resource_type="video", first_seen_at=NOW, fetched_at=NOW
    )
    with repo.connect() as conn:
        assert repo.insert_resource(conn, res) is True
        assert repo.insert_resource(conn, res) is False  # already present
        conn.commit()
        assert repo.existing_resource_ids(conn, "s1") == {"res1"}


def test_resource_repoll_refreshes_metadata_without_counting_as_new(tmp_path):
    repo = _repo_with_source(tmp_path)
    first = IntelResource(
        id="res1",
        source_id="s1",
        resource_type="atc_ad",
        title="Old title",
        first_seen_at=NOW,
        fetched_at=NOW,
        metadata={"format": "image", "image_sources": []},
    )
    refreshed = first.model_copy(
        update={
            "title": "New title",
            "fetched_at": datetime(2026, 6, 10, 13, 0, tzinfo=UTC),
            "metadata": {
                "format": "image",
                "image_sources": ["https://tpc.googlesyndication.com/archive/simgad/123"],
            },
        }
    )

    with repo.connect() as conn:
        assert repo.insert_resource(conn, first) is True
        assert repo.insert_resource(conn, refreshed) is False
        conn.commit()
        got = repo.list_resources(conn, source_id="s1")[0]

    assert got.title == "New title"
    assert got.first_seen_at == NOW
    assert got.metadata["image_sources"] == [
        "https://tpc.googlesyndication.com/archive/simgad/123"
    ]


def test_signal_round_trip(tmp_path):
    repo = _repo_with_source(tmp_path)
    sig = IntelSignal(
        id="sig1",
        brand_name="Toyota",
        signal_type="new_ad_upload",
        status="candidate",
        confidence=0.5,
        title="A new spot",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    with repo.connect() as conn:
        assert repo.insert_signal(conn, sig) is True
        assert repo.insert_signal(conn, sig) is False  # idempotent
        conn.commit()
        got = repo.get_signal(conn, "sig1")
        assert got is not None and got.title == "A new spot"
        assert [s.id for s in repo.list_signals(conn, brand="Toyota")] == ["sig1"]
        assert repo.list_signals(conn, brand="Honda") == []


def test_lease_is_single_flight(tmp_path):
    repo = _repo_with_source(tmp_path)
    with repo.connect() as conn:
        assert repo.acquire_lease(conn, "s1", "owner1", now=NOW, ttl_seconds=600) is True
        # A different owner cannot take a held, unexpired lease.
        assert repo.acquire_lease(conn, "s1", "owner2", now=NOW, ttl_seconds=600) is False
        # Same owner may re-acquire (re-entrant).
        assert repo.acquire_lease(conn, "s1", "owner1", now=NOW, ttl_seconds=600) is True
        repo.release_lease(conn, "s1")
        assert repo.acquire_lease(conn, "s1", "owner2", now=NOW, ttl_seconds=600) is True


def test_campaign_group_is_stable(tmp_path):
    repo = _repo_with_source(tmp_path)
    with repo.connect() as conn:
        first = repo.get_or_create_campaign_group(
            conn,
            brand_name="Toyota",
            group_key="toyota|camry reborn|2026-w24",
            title="Camry",
            now=NOW,
        )
        again = repo.get_or_create_campaign_group(
            conn,
            brand_name="Toyota",
            group_key="toyota|camry reborn|2026-w24",
            title="Camry",
            now=NOW,
        )
        assert first == again
        assert repo.group_signal_count(conn, first) == 0
