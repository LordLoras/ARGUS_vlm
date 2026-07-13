from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ad_classifier.api.routes.intelligence import router
from ad_classifier.intelligence_crawler.config import IntelConfig, SourceConfig, WatchlistConfig
from ad_classifier.intelligence_crawler.manager import IntelManager
from ad_classifier.intelligence_crawler.models import IntelEvidence, IntelResource, IntelSignal

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)


def _client(tmp_path, *, screenshot_path: str | None = None) -> TestClient:
    config = IntelConfig(
        db_path=tmp_path / "intel.db",
        cache_dir=tmp_path / "cache",
        watchlist=WatchlistConfig(
            include_graph_brands=False, entity_graph_db_path=None, seed_brands=["Toyota"]
        ),
        sources=[
            SourceConfig(id="s1", brand="Toyota", source_type="mock", tier="A", enabled=False)
        ],
    )
    manager = IntelManager(config)
    # Seed one resource + signal with evidence directly through the repository.
    resource = IntelResource(
        id="res_demo",
        source_id="s1",
        resource_type="meta_ad",
        url="https://www.facebook.com/ads/library/?id=123",
        platform="meta",
        platform_id="123",
        title="Toyota: Camry Reborn",
        description="Visible Meta card copy",
        published_at=NOW,
        first_seen_at=NOW,
        fetched_at=NOW,
        is_backfill=True,
        metadata={
            "screenshot_path": screenshot_path or "C:/tmp/card_123.png",
            "image_sources": ["https://cdn.example/image.jpg"],
            "video_sources": ["https://cdn.example/video.mp4"],
            "links": [{"text": "Toyota", "href": "https://toyota.com"}],
        },
    )
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
                resource_id="res_demo",
                source_id="s1",
                evidence_type="video",
                url="https://www.youtube.com/watch?v=VID1",
                text="Camry Reborn",
                confidence=0.9,
            )
        ],
    )
    with manager.repo.connect() as conn:
        manager.repo.sync_sources(conn, [source.to_source() for source in config.sources])
        manager.repo.insert_resource(conn, resource)
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

    adapters = client.get("/api/intelligence/adapters").json()["items"]
    meta = next(item for item in adapters if item["source_type"] == "meta_ad_library_ui")
    assert meta["label"] == "Meta Ad Library"
    assert "card screenshots" in meta["provides"]
    google = next(item for item in adapters if item["source_type"] == "google_atc")
    assert google["config"]["max_pages"] == 0


def test_brand_and_resource_artifact_endpoints(tmp_path):
    client = _client(tmp_path)
    manager = client.app.state.intel_manager
    with manager.repo.connect() as conn:
        manager.repo.update_source_state(
            conn,
            "s1",
            state_json={
                "google_atc": {
                    "checkpoint": {
                        "token": "opaque-secret-cursor",
                        "page_count": 8,
                    }
                }
            },
        )
        conn.commit()

    brands = client.get("/api/intelligence/brands").json()["items"]
    toyota = next(item for item in brands if item["brand_name"] == "Toyota")
    assert toyota["source_count"] == 1
    assert toyota["resource_count"] == 1
    assert toyota["backfill_resource_count"] == 1
    assert toyota["signal_count"] == 1
    assert toyota["artifact_summary"]["screenshot_count"] == 1
    assert toyota["artifact_summary"]["image_source_count"] == 1

    resource_page = client.get("/api/intelligence/resources", params={"brand": "Toyota"}).json()
    resources = resource_page["items"]
    assert resource_page["total"] == 1
    assert resource_page["next_offset"] is None
    assert [resource["id"] for resource in resources] == ["res_demo"]
    assert resources[0]["normalized"]["provider"] == "mock"
    assert resources[0]["normalized"]["advertiser"]["name"] == "Toyota"
    assert resources[0]["normalized"]["variants"][0]["landing_url"] == "https://toyota.com"
    artifact_types = {artifact["artifact_type"] for artifact in resources[0]["artifacts"]}
    assert {"card_screenshot", "image_url", "video_url", "link"} <= artifact_types
    assert client.get("/api/intelligence/resources/res_demo").json()["id"] == "res_demo"

    statuses = client.get("/api/intelligence/source-statuses").json()["items"]
    assert statuses[0]["source"]["id"] == "s1"
    assert statuses[0]["state"]["last_outcome"] is None
    assert statuses[0]["resume_available"] is False
    assert statuses[0]["resume_page"] is None
    assert "provider_state" not in statuses[0]["state"]
    assert "opaque-secret-cursor" not in str(statuses[0])


def test_resource_screenshot_endpoint(tmp_path):
    shot = tmp_path / "cache" / "meta_ad_library_ui" / "s1" / "card_123.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    client = _client(tmp_path, screenshot_path=str(shot))

    ok = client.get("/api/intelligence/resources/res_demo/screenshot")
    assert ok.status_code == 200
    assert ok.content.startswith(b"\x89PNG")

    assert client.get("/api/intelligence/resources/missing/screenshot").status_code == 404


def test_resource_screenshot_rejects_paths_outside_cache(tmp_path):
    # A stored path outside the crawler cache (or a traversal attempt) must never be served.
    outside = tmp_path / "elsewhere" / "card.png"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    client = _client(tmp_path, screenshot_path=str(outside))

    assert client.get("/api/intelligence/resources/res_demo/screenshot").status_code == 404


def test_crawl_endpoint_runs(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/intelligence/crawl", json={"due": True})
    assert resp.status_code == 200
    # No enabled sources -> a clean, empty run.
    assert resp.json()["status"] in {"completed", "degraded"}


def test_queued_crawl_returns_immediately_addressable_run(tmp_path):
    client = _client(tmp_path)
    response = client.post("/api/intelligence/crawl/queue", json={"due": True})

    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "queued"
    run = client.get(f"/api/intelligence/runs/{queued['run_id']}")
    assert run.status_code == 200
    # The API owns no execution thread; the independent worker claims this durable row.
    assert run.json()["status"] == "queued"


def test_queue_idempotency_health_cursor_and_exports(tmp_path):
    client = _client(tmp_path)
    headers = {"Idempotency-Key": "demo-click-1"}
    first = client.post("/api/intelligence/crawl/queue", json={"due": True}, headers=headers)
    second = client.post("/api/intelligence/crawl/queue", json={"due": True}, headers=headers)
    assert first.json()["run_id"] == second.json()["run_id"]

    health = client.get("/api/intelligence/health").json()
    assert health["status"] == "critical"
    assert health["queue"]["queued"] == 1
    assert any(issue["code"] == "worker_unavailable" for issue in health["issues"])

    manager = client.app.state.intel_manager
    with manager.repo.connect() as conn:
        manager.repo.insert_resource(
            conn,
            IntelResource(
                id="res_older",
                source_id="s1",
                resource_type="meta_ad",
                title="Older creative",
                first_seen_at=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
                fetched_at=datetime(2026, 6, 23, 12, 0, tzinfo=UTC),
            ),
        )
        conn.commit()

    page_one = client.get("/api/intelligence/resources", params={"limit": 1}).json()
    assert page_one["schema_version"] == "1.0"
    assert page_one["next_cursor"]
    page_two = client.get(
        "/api/intelligence/resources",
        params={"limit": 1, "cursor": page_one["next_cursor"]},
    ).json()
    assert page_two["items"][0]["id"] != page_one["items"][0]["id"]

    exported = client.get("/api/intelligence/resources/export", params={"format": "json"})
    assert exported.status_code == 200
    assert exported.json()["schema_version"] == "1.0"
    assert len(exported.json()["items"]) == 2
    jsonl = client.get("/api/intelligence/resources/export", params={"format": "jsonl"})
    assert len([line for line in jsonl.text.splitlines() if line]) == 2

    with manager.repo.connect() as conn:
        manager.repo.create_run(conn, "intel_run_change")
        manager.repo.insert_resource_change(
            conn,
            change_id="chg_demo",
            resource_id="res_demo",
            source_id="s1",
            run_id="intel_run_change",
            change_type="updated",
            changed_at=NOW,
            content_hash="new-hash",
            previous_content_hash="old-hash",
        )
        conn.commit()
    feed = client.get("/api/intelligence/resources/changes", params={"since": "365d"}).json()
    assert feed["items"][0]["change_type"] == "updated"
    assert feed["items"][0]["resource"]["id"] == "res_demo"


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
    assert source["tier"] == "C"  # provider reliability tier is canonical

    listed = client.get("/api/intelligence/sources").json()["items"]
    assert any(s["id"] == sid for s in listed)
    enabled = client.get("/api/intelligence/sources", params={"enabled_only": True}).json()["items"]
    assert any(s["id"] == sid for s in enabled)

    disabled = client.patch(f"/api/intelligence/sources/{sid}", json={"enabled": False})
    assert disabled.status_code == 200 and disabled.json()["enabled"] is False

    archived = client.delete(f"/api/intelligence/sources/{sid}")
    assert archived.status_code == 200 and archived.json() == {"archived": sid}
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


def test_mutations_require_optional_service_key(tmp_path, monkeypatch):
    client = _client(tmp_path)
    monkeypatch.setenv("INTELLIGENCE_CRAWLER_API_KEY", "demo-secret")

    denied = client.post("/api/intelligence/crawl", json={"due": True})
    assert denied.status_code == 401

    allowed = client.post(
        "/api/intelligence/crawl",
        json={"due": True},
        headers={"X-Intelligence-Key": "demo-secret"},
    )
    assert allowed.status_code == 200
    run_id = allowed.json()["run_id"]
    assert client.get(f"/api/intelligence/runs/{run_id}").status_code == 200
