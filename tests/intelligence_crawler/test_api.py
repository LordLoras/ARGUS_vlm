from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ad_classifier.api.routes.intelligence import router
from ad_classifier.intelligence_crawler.config import IntelConfig, SourceConfig, WatchlistConfig
from ad_classifier.intelligence_crawler.manager import IntelManager
from ad_classifier.intelligence_crawler.models import IntelEvidence, IntelSignal

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)


def _client(tmp_path) -> TestClient:
    config = IntelConfig(
        db_path=tmp_path / "intel.db",
        watchlist=WatchlistConfig(
            include_graph_brands=False, entity_graph_db_path=None, seed_brands=["Toyota"]
        ),
        sources=[
            SourceConfig(id="s1", brand="Toyota", source_type="mock", tier="A", enabled=False)
        ],
    )
    manager = IntelManager(config)
    # Seed one signal with evidence directly through the repository.
    signal = IntelSignal(
        id="sig_demo",
        brand_name="Toyota",
        signal_type="new_ad_upload",
        status="corroborated",
        confidence=0.9,
        title="Camry Reborn — Official",
        campaign_name="Camry Reborn",
        first_seen_at=NOW,
        source_published_at=NOW,
        last_seen_at=NOW,
        evidence=[
            IntelEvidence(
                id="ev1",
                signal_id="sig_demo",
                evidence_type="video",
                url="https://www.youtube.com/watch?v=VID1",
                text="Camry Reborn",
                confidence=0.9,
            )
        ],
    )
    with manager.repo.connect() as conn:
        manager.repo.insert_signal(conn, signal)
        conn.commit()

    app = FastAPI()
    app.state.intel_manager = manager
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_list_and_detail_signals(tmp_path):
    client = _client(tmp_path)

    listing = client.get("/api/intelligence/signals", params={"brand": "Toyota"})
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert [i["id"] for i in items] == ["sig_demo"]

    detail = client.get("/api/intelligence/signals/sig_demo")
    assert detail.status_code == 200
    body = detail.json()
    assert body["campaign_name"] == "Camry Reborn"
    # Detail hydrates evidence (list endpoint does not).
    assert body["evidence"][0]["url"] == "https://www.youtube.com/watch?v=VID1"

    assert client.get("/api/intelligence/signals/missing").status_code == 404


def test_digest_and_source_types(tmp_path):
    client = _client(tmp_path)

    digest = client.get("/api/intelligence/digest", params={"since": "30d"})
    assert digest.status_code == 200
    entries = digest.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["evidence_urls"] == ["https://www.youtube.com/watch?v=VID1"]

    types = client.get("/api/intelligence/source-types").json()["source_types"]
    assert {"mock", "rss", "youtube_channel", "meta_ad_library_ui"} <= set(types)


def test_crawl_endpoint_runs(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/intelligence/crawl", json={"due": True})
    assert resp.status_code == 200
    # No enabled sources -> a clean, empty run.
    assert resp.json()["status"] in {"completed", "degraded"}


def test_source_crud_api(tmp_path):
    client = _client(tmp_path)

    created = client.post(
        "/api/intelligence/sources",
        json={
            "brand": "Toyota",
            "source_type": "rss",
            "tier": "A",
            "url": "https://pressroom.toyota.com/product/feed/",
            "enabled": True,
        },
    )
    assert created.status_code == 200
    source = created.json()
    sid = source["id"]
    assert source["brand_name"] == "Toyota" and source["enabled"] is True

    listed = client.get("/api/intelligence/sources").json()["items"]
    assert any(s["id"] == sid for s in listed)
    enabled = client.get("/api/intelligence/sources", params={"enabled_only": True}).json()["items"]
    assert any(s["id"] == sid for s in enabled)

    disabled = client.patch(f"/api/intelligence/sources/{sid}", json={"enabled": False})
    assert disabled.status_code == 200 and disabled.json()["enabled"] is False

    assert client.delete(f"/api/intelligence/sources/{sid}").status_code == 200
    assert (
        client.patch(f"/api/intelligence/sources/{sid}", json={"enabled": True}).status_code == 404
    )


def test_source_delete_reports_busy_database(tmp_path, monkeypatch):
    client = _client(tmp_path)
    manager = client.app.state.intel_manager

    def locked(_source_id: str) -> bool:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(manager, "delete_source", locked)

    response = client.delete("/api/intelligence/sources/source_under_crawl")

    assert response.status_code == 409
    assert "database is busy" in response.json()["detail"]
