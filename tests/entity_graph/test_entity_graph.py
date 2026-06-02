from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from ad_classifier.api.app import create_app
from ad_classifier.db.connection import open_database, open_readonly_database
from ad_classifier.entity_graph.manager import EntityGraphManager
from ad_classifier.entity_graph.repository import EntityGraphRepository


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    config = {
        "paths": {
            "data_root": str(data_root),
            "uploads": str(data_root / "uploads"),
            "frames": str(data_root / "frames"),
            "audio": str(data_root / "audio"),
            "whisper": str(data_root / "whisper"),
            "out": str(data_root / "out"),
            "sqlite_path": str(tmp_path / "submitted.db"),
            "entity_graph_path": str(tmp_path / "entity_graph.db"),
        },
        "api": {"cors_origins": ["http://localhost:5173"]},
        "vector_store": {"text_dim": 8, "visual_dim": 8},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def _paths(config_path: Path) -> tuple[Path, Path]:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return Path(data["paths"]["sqlite_path"]), Path(data["paths"]["entity_graph_path"])


def _seed_ads(config_path: Path) -> None:
    submitted_db, _graph_db = _paths(config_path)
    conn = open_database(submitted_db)
    try:
        now = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT INTO ads (
              id, source_path, ingested_at, status, brand_name, advertiser_name,
              products_text, primary_category, subcategory, iab_unique_id,
              iab_selected_category, iab_full_path, iab_content_ids, iab_content_paths
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_wrangle",
                "/tmp/wrangler.mp4",
                now,
                "completed",
                "Jeep",
                "Stellantis",
                "Wrangler",
                "automotive",
                "SUV",
                "1028",
                "Sport Utility Vehicles",
                "Vehicles > Sport Utility Vehicles",
                "483,641",
                "Autos & Vehicles | Shopping",
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, advertiser_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "ad_wrangle",
                '{"name":"Jeep","confidence":0.9}',
                '["Wrangler"]',
                '{"advertiser_name":"Stellantis","parent_company":"Stellantis"}',
            ),
        )
        conn.execute(
            """
            INSERT INTO ads (
              id, source_path, ingested_at, status, products_text, primary_category
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("ad_weak", "/tmp/weak.mp4", now, "completed", "Mystery Item", "other"),
        )
        conn.commit()
    finally:
        conn.close()


def test_graph_repository_persists_nodes_edges_and_mappings(tmp_path: Path) -> None:
    repo = EntityGraphRepository(tmp_path / "entity_graph.db")
    with repo.connect() as conn:
        source = repo.upsert_source(
            conn, source_type="submitted_ad", label="Submitted ad", ad_id="ad_one"
        )
        product, created = repo.upsert_node(
            conn,
            entity_type="product",
            canonical_name="Wrangler",
            status="confirmed_unreviewed",
            confidence=0.88,
        )
        brand, _ = repo.upsert_node(
            conn,
            entity_type="brand",
            canonical_name="Jeep",
            status="confirmed_unreviewed",
            confidence=0.9,
        )
        repo.upsert_edge(
            conn,
            source_node_id=product.id,
            target_node_id=brand.id,
            relation="BRANDED_BY",
            confidence=0.9,
            status="confirmed_unreviewed",
            source_id=source.id,
        )
        repo.upsert_taxonomy_mapping(
            conn,
            entity_id=product.id,
            taxonomy_type="product",
            taxonomy_id="1028",
            taxonomy_name="Sport Utility Vehicles",
            confidence=0.74,
            status="confirmed_unreviewed",
            source_id=source.id,
            evidence_text="Wrangler",
        )
        conn.commit()

    with repo.connect(readonly=True) as conn:
        products = repo.list_products(conn)
        assert created is True
        assert products[0].node.canonical_name == "Wrangler"
        assert products[0].brand and products[0].brand.canonical_name == "Jeep"
        assert products[0].taxonomy_mappings_count == 1


def test_resolver_uses_submitted_db_readonly_and_separates_candidates(config_path: Path) -> None:
    app = create_app(config_path=config_path)
    _seed_ads(config_path)
    _submitted_db, graph_db = _paths(config_path)
    manager = EntityGraphManager(graph_db, _submitted_db)

    assert manager.submitted_db_is_readonly() is True
    readonly = open_readonly_database(_submitted_db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            readonly.execute(
                "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                ("ad_forbidden", "/tmp/nope.mp4"),
            )
    finally:
        readonly.close()

    preview = manager.preview_resolver(limit=10)
    by_product = {item.product_name: item for item in preview.items}
    assert by_product["Wrangler"].status == "confirmed_unreviewed"
    assert by_product["Mystery Item"].status == "candidate"

    result = manager.run_resolver(limit=10)
    assert result.confirmed_unreviewed_count == 1
    assert result.candidate_count == 1

    products = manager.list_products(limit=10)
    wrangler = next(item for item in products if item.node.canonical_name == "Wrangler")
    assert "submitted ad observation" in (wrangler.node.description or "")
    assert wrangler.related_ads_count == 1


def test_entity_graph_api_product_detail_and_candidate_discovery(config_path: Path) -> None:
    app = create_app(config_path=config_path)
    _seed_ads(config_path)
    client = TestClient(app)

    readonly = client.get("/api/entity-graph/readonly-status")
    assert readonly.status_code == 200
    assert readonly.json()["submitted_db_query_only"] is True

    run = client.post("/api/entity-graph/resolver/run", json={"limit": 10})
    assert run.status_code == 200, run.text

    listed = client.get("/api/entity-graph/products")
    assert listed.status_code == 200
    products = listed.json()["items"]
    wrangler = next(item for item in products if item["node"]["canonical_name"] == "Wrangler")

    detail = client.get(f"/api/entity-graph/products/{wrangler['node']['id']}")
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["brand"]["canonical_name"] == "Jeep"
    assert payload["owner"]["canonical_name"] == "Stellantis"
    assert len(payload["taxonomy_mappings"]) == 3
    assert payload["related_ads"][0]["ad_id"] == "ad_wrangle"

    reviewed = client.post(f"/api/entity-graph/entities/{wrangler['node']['id']}/promote")
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "confirmed_reviewed"

    discovery = client.post(
        "/api/entity-graph/discovery-candidates",
        json={
            "entity_type": "product",
            "name": "Search Result Only Product",
            "source_url": "https://example.test/product",
            "confidence": 0.95,
        },
    )
    assert discovery.status_code == 200, discovery.text
    assert discovery.json()["status"] == "candidate"

    candidates = client.get("/api/entity-graph/products", params={"status": "candidate"})
    assert any(
        item["node"]["canonical_name"] == "Search Result Only Product"
        for item in candidates.json()["items"]
    )
