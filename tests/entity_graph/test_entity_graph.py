from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ad_classifier.api.app import create_app
from ad_classifier.cli import app as cli_app
from ad_classifier.db.connection import open_database, open_readonly_database
from ad_classifier.entity_graph.crawler import EntityWebCrawler, FetchedPage
from ad_classifier.entity_graph.discovery_vlm import DiscoveryProductFact, DiscoveryVLMResult
from ad_classifier.entity_graph.manager import EntityGraphManager
from ad_classifier.entity_graph.models import IngestAssistRequest
from ad_classifier.entity_graph.repository import EntityGraphRepository
from ad_classifier.entity_graph.targets import from_ad_url_mapping


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
                "Jeep Wrangler",
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
                '["Jeep Wrangler"]',
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


def _seed_noisy_products(config_path: Path) -> None:
    submitted_db, _graph_db = _paths(config_path)
    conn = open_database(submitted_db)
    try:
        now = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT INTO ads (
              id, source_path, ingested_at, status, brand_name, advertiser_name,
              products_text, primary_category, subcategory, website_domain, landing_page_domain
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_ford_trucks",
                "/tmp/ford.mp4",
                now,
                "completed",
                "Ford",
                "Barton Ford",
                "vehicles, trucks, F-150, 2026 F-150 XLT Hybrid, Ford Bronco",
                "automotive",
                "Trucks",
                "ford.example",
                "ford.example",
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, advertiser_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "ad_ford_trucks",
                '{"name":"Ford","confidence":0.9}',
                '["vehicles","trucks","F-150","2026 F-150 XLT Hybrid","Ford Bronco"]',
                '{"advertiser_name":"Barton Ford","parent_company":"Barton Ford"}',
            ),
        )
        conn.execute(
            """
            INSERT INTO ads (
              id, source_path, ingested_at, status, brand_name, advertiser_name,
              products_text, primary_category, subcategory
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_buick_envista",
                "/tmp/envista.mp4",
                now,
                "completed",
                "GMC",
                "King Cadillac Buick GMC",
                "2026 Buick Envista",
                "automotive",
                "SUV",
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, advertiser_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "ad_buick_envista",
                '{"name":"GMC","confidence":0.8}',
                '["2026 Buick Envista"]',
                '{"advertiser_name":"King Cadillac Buick GMC","parent_company":"King Cadillac Buick GMC"}',
            ),
        )
        conn.execute(
            """
            INSERT INTO ads (
              id, source_path, ingested_at, status, brand_name, advertiser_name,
              products_text, primary_category, subcategory
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_ford_variant",
                "/tmp/ford-lightning.mp4",
                now,
                "completed",
                "Ford",
                "Ford",
                "F-150 Lightning",
                "automotive",
                "Truck",
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, advertiser_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "ad_ford_variant",
                '{"name":"Ford","confidence":0.9}',
                '["F-150 Lightning"]',
                '{"advertiser_name":"Ford","parent_company":"Ford"}',
            ),
        )
        conn.execute(
            """
            INSERT INTO ads (
              id, source_path, ingested_at, status, brand_name, advertiser_name,
              products_text, primary_category, subcategory
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_gmc_base",
                "/tmp/gmc-base.mp4",
                now,
                "completed",
                "GMC",
                "GMC",
                "Sierra HD",
                "automotive",
                "Truck",
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, advertiser_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "ad_gmc_base",
                '{"name":"GMC","confidence":0.9}',
                '["Sierra HD"]',
                '{"advertiser_name":"GMC","parent_company":"GM"}',
            ),
        )
        conn.execute(
            """
            INSERT INTO ads (
              id, source_path, ingested_at, status, brand_name, advertiser_name,
              products_text, primary_category, subcategory
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_gmc_variants",
                "/tmp/gmc-variants.mp4",
                now,
                "completed",
                "GMC",
                "GMC",
                "Sierra 3500 HD, Sierra Heavy Duty",
                "automotive",
                "Truck",
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, advertiser_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "ad_gmc_variants",
                '{"name":"GMC","confidence":0.9}',
                '["Sierra 3500 HD","Sierra Heavy Duty"]',
                '{"advertiser_name":"GMC","parent_company":"GM"}',
            ),
        )
        conn.execute(
            """
            INSERT INTO ads (
              id, source_path, ingested_at, status, brand_name, advertiser_name,
              products_text, primary_category, subcategory
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_credit_union",
                "/tmp/credit.mp4",
                now,
                "completed",
                "Wright-Patt Credit Union",
                "Wright-Patt Credit Union",
                "Credit union membership, banking services",
                "financial services",
                "credit union",
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, advertiser_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "ad_credit_union",
                '{"name":"Wright-Patt Credit Union","confidence":0.8}',
                '["Credit union membership","banking services"]',
                '{"advertiser_name":"Wright-Patt Credit Union","parent_company":"Wright-Patt Credit Union"}',
            ),
        )
        conn.execute(
            """
            INSERT INTO ads (
              id, source_path, ingested_at, status, brand_name, advertiser_name,
              products_text, primary_category, subcategory, website_domain, landing_page_domain
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_tmobile_iphone",
                "/tmp/iphone.mp4",
                now,
                "completed",
                "T-Mobile",
                "T-Mobile",
                "iPhone 17 Pro",
                "telecom",
                "mobile_service",
                None,
                None,
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, advertiser_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                "ad_tmobile_iphone",
                '{"name":"T-Mobile","confidence":0.9}',
                '["iPhone 17 Pro"]',
                '{"advertiser_name":"T-Mobile","parent_company":"T-Mobile US, Inc."}',
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_publisher_overlay_target(config_path: Path) -> None:
    submitted_db, _graph_db = _paths(config_path)
    conn = open_database(submitted_db)
    try:
        now = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT INTO ads (
              id, source_path, ingested_at, status, brand_name, advertiser_name,
              products_text, primary_category, subcategory, website_domain, landing_page_domain
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_wbal_overlay",
                "/tmp/wbal-ford.mp4",
                now,
                "completed",
                "Ford",
                "Ford",
                "F-150",
                "automotive",
                "pickup truck",
                "wbaltv.com",
                "wbaltv.com",
            ),
        )
        conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, advertiser_json,
              contact_points_json, landing_page_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "ad_wbal_overlay",
                '{"name":"Ford","confidence":0.9}',
                '["F-150"]',
                '{"advertiser_name":"Ford","parent_company":"Ford"}',
                """
                {
                  "websites": [
                    {
                      "url": "https://WBALTV.com",
                      "domain": "wbaltv.com",
                      "display_text": "WBALTV.com",
                      "evidence": [
                        {
                          "time_ms": 0,
                          "frame_index": 0,
                          "source": "ocr",
                          "text": "C4 & BRYAN NEHMAN 5:53 WBALTV.com news and ticket giveaway",
                          "confidence": 0.9
                        }
                      ]
                    }
                  ],
                  "phone_numbers": [],
                  "social_handles": [],
                  "app_store_links": [],
                  "qr_codes": []
                }
                """,
                """
                {
                  "url": "https://WBALTV.com",
                  "domain": "wbaltv.com",
                  "evidence": [
                    {
                      "time_ms": 0,
                      "frame_index": 0,
                      "source": "ocr",
                      "text": "C4 & BRYAN NEHMAN 5:53 WBALTV.com news and ticket giveaway",
                      "confidence": 0.9
                    }
                  ]
                }
                """,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _write_entity_crawler_config(config_path: Path) -> Path:
    path = config_path.parent / "entity_crawler.yaml"
    path.write_text(
        r"""
crawler:
  enabled: true
  provider: http
vlm_parse:
  enabled: true
  write_mode: candidate_only
resolver:
  strip_leading_model_year: true
  strip_context_brand_prefix: true
  collapse_variants_when_base_observed: true
  min_unmatched_name_chars: 3
  drop_exact:
    - vehicle
    - vehicles
    - truck
    - trucks
  context_prefix_stopwords:
    - bank
    - banking
    - credit
    - union
  ad_context_category_exact:
    - car_dealership
    - mobile_service
""",
        encoding="utf-8",
    )
    return path


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
    create_app(config_path=config_path)
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
    assert by_product["Wrangler"].category_name == "IAB Product 1028: Sport Utility Vehicles"
    assert by_product["Mystery Item"].status == "candidate"

    result = manager.run_resolver(limit=10)
    assert result.confirmed_unreviewed_count == 1
    assert result.candidate_count == 1

    products = manager.list_products(limit=10)
    wrangler = next(item for item in products if item.node.canonical_name == "Wrangler")
    assert "submitted ad observation" in (wrangler.node.description or "")
    assert wrangler.related_ads_count == 1


def test_resolver_uses_crawler_config_for_generic_product_cleanup(config_path: Path) -> None:
    create_app(config_path=config_path)
    _seed_noisy_products(config_path)
    submitted_db, graph_db = _paths(config_path)
    crawler_config_path = _write_entity_crawler_config(config_path)
    manager = EntityGraphManager(
        graph_db,
        submitted_db,
        crawler_config_path=crawler_config_path,
    )

    preview = manager.preview_resolver(limit=10)
    by_product = {item.product_name: item for item in preview.items}
    assert "vehicles" not in by_product
    assert "trucks" not in by_product
    assert "2026 F-150 XLT Hybrid" not in by_product
    assert "F-150 Lightning" not in by_product
    assert "Sierra 3500 HD" not in by_product
    assert "Sierra Heavy Duty" not in by_product
    assert by_product["F-150"].brand_name is None
    assert by_product["F-150"].category_name is None
    assert by_product["Bronco"].brand_name == "Ford"
    assert by_product["Sierra HD"].brand_name is None
    assert by_product["Envista"].brand_name == "Buick"
    assert by_product["Credit union membership"].brand_name is None
    assert by_product["iPhone 17 Pro"].brand_name is None

    manager.run_resolver(limit=10)
    products = manager.list_products(limit=20)
    names = {item.node.canonical_name for item in products}
    assert {"F-150", "Bronco", "Envista"} <= names
    assert "vehicles" not in names
    assert "trucks" not in names
    iphone = next(item for item in products if item.node.canonical_name == "iPhone 17 Pro")
    iphone_detail = manager.get_product(iphone.node.id)
    assert iphone_detail is not None
    assert iphone_detail.brand is None
    assert "submitted ad brand/advertiser context T-Mobile" in (
        iphone_detail.node.description or ""
    )
    assert iphone_detail.category is None
    assert "submitted ad category context mobile_service" in (
        iphone_detail.node.description or ""
    )

    f150 = next(item for item in products if item.node.canonical_name == "F-150")
    detail = manager.get_product(f150.node.id)
    assert detail is not None
    assert detail.category is None
    aliases = {item.alias for item in detail.aliases}
    assert "2026 F-150 XLT Hybrid" in aliases
    assert "F-150 Lightning" in aliases
    assert len({item.normalized_alias for item in detail.aliases}) == len(detail.aliases)
    assert any(obs.field == "unmapped_category_hint" for obs in detail.observations)

    sierra = next(item for item in products if item.node.canonical_name == "Sierra HD")
    sierra_detail = manager.get_product(sierra.node.id)
    assert sierra_detail is not None
    sierra_aliases = {item.alias for item in sierra_detail.aliases}
    assert "Sierra 3500 HD" in sierra_aliases
    assert "Sierra Heavy Duty" in sierra_aliases


class _FakeFetcher:
    def fetch(self, target, config):
        if target.ad_id == "ad_tmobile_iphone":
            return FetchedPage(
                url=target.url,
                final_url=target.url,
                status_code=200,
                title="Apple iPhone 17 Pro deals from T-Mobile",
                description="Buy Apple iPhone 17 Pro on the T-Mobile network.",
                text="Apple iPhone 17 Pro smartphone available with T-Mobile carrier offers.",
                fetcher="fake",
            )
        return FetchedPage(
            url=target.url,
            final_url=target.url,
            status_code=200,
            title="Ford F-150 and Bronco dealer inventory",
            description="Discovery-only test page",
            text="Shop Ford F-150 trucks and Ford Bronco SUVs at this dealer.",
            fetcher="fake",
        )


class _FakeDiscoveryVerifier:
    def verify(self, *, source_url, final_url, title, description, text, products, submitted_ad=None):
        if any(product.canonical_name == "iPhone 17 Pro" for product in products):
            return DiscoveryVLMResult(
                source_url=source_url,
                source_kind="carrier",
                product_facts=[
                    DiscoveryProductFact(
                        matched_submitted_product="iPhone 17 Pro",
                        product_name="iPhone 17 Pro",
                        brand_name="Apple",
                        brand_description="Apple designs iPhone hardware and software products.",
                        owner_name="Apple Inc.",
                        owner_description="Apple Inc. is the company behind iPhone.",
                        category_name="smartphone",
                        relation_to_page="carrier_offer",
                        confidence=0.86,
                        evidence_spans=["Apple iPhone 17 Pro smartphone available with T-Mobile carrier offers."],
                        warnings=["web_only", "seller_not_manufacturer"],
                    )
                ],
                suggested_ad_changes=[
                    {
                        "field_path": "ads.brand_name",
                        "current_value": "T-Mobile",
                        "suggested_value": "Apple",
                        "confidence": 0.9,
                        "reason": "Carrier page mentions Apple iPhone.",
                        "evidence_spans": ["Apple iPhone 17 Pro smartphone available with T-Mobile carrier offers."],
                        "apply_safety": "safe_projection_update",
                    }
                ],
            )
        return DiscoveryVLMResult(
            source_url=source_url,
            source_kind="manufacturer",
            product_facts=[
                DiscoveryProductFact(
                    matched_submitted_product=product.canonical_name,
                    product_name=product.canonical_name,
                    brand_name="Ford" if product.canonical_name in {"F-150", "Bronco"} else None,
                    category_name="truck" if product.canonical_name == "F-150" else None,
                    relation_to_page="manufacturer_page",
                    confidence=0.82,
                    evidence_spans=[f"Discovery-only page mentions {product.canonical_name}."],
                    warnings=["web_only"],
                )
                for product in products
                if product.canonical_name in {"F-150", "Bronco"}
            ],
            suggested_ad_changes=[
                {
                    "field_path": "ads.subcategory",
                    "current_value": submitted_ad.subcategory if submitted_ad else "Trucks",
                    "suggested_value": "pickup truck",
                    "confidence": 0.83,
                    "reason": "Manufacturer page evidence describes F-150 as a pickup truck.",
                    "evidence_spans": ["Shop Ford F-150 trucks and Ford Bronco SUVs at this dealer."],
                    "apply_safety": "safe_projection_update",
                }
            ],
        )


def test_reset_and_crawler_rebuild_with_discovery_only_sources(config_path: Path) -> None:
    create_app(config_path=config_path)
    _seed_noisy_products(config_path)
    submitted_db, graph_db = _paths(config_path)
    crawler_config_path = _write_entity_crawler_config(config_path)
    manager = EntityGraphManager(
        graph_db,
        submitted_db,
        crawler_config_path=crawler_config_path,
    )
    ford_targets = [
        target
        for target in manager.submitted_ads.list_web_targets(limit=10)
        if target.ad_id == "ad_ford_trucks"
    ]
    assert [target.url for target in ford_targets] == ["https://ford.example"]

    manager.run_resolver(limit=10)
    assert manager.list_products(limit=20)

    assert manager.reset_graph() == {"reset": True}
    assert manager.list_products(limit=20) == []
    assert manager.submitted_ads.list_product_observations(limit=10)

    crawler = EntityWebCrawler(
        manager.graph,
        manager.submitted_ads,
        manager.crawler_config,
        fetcher=_FakeFetcher(),
        verifier=_FakeDiscoveryVerifier(),
    )
    result = crawler.run(
        limit=10,
        ad_ids=["ad_ford_trucks", "ad_tmobile_iphone"],
        extra_targets=from_ad_url_mapping(
            {"ad_tmobile_iphone": ["https://www.apple.example/iphone-17-pro"]}
        ),
    )
    repeat_result = crawler.run(
        limit=10,
        ad_ids=["ad_tmobile_iphone"],
        extra_targets=from_ad_url_mapping(
            {"ad_tmobile_iphone": ["https://www.apple.example/iphone-17-pro"]}
        ),
    )
    assert result.visited_count >= 1
    assert repeat_result.visited_count >= 1
    assert result.observation_count >= 2
    assert result.suggestion_count >= 1

    products = manager.list_products(limit=20)
    f150 = next(item for item in products if item.node.canonical_name == "F-150")
    detail = manager.get_product(f150.node.id)
    assert detail is not None
    assert f150.node.status == "confirmed_unreviewed"
    assert any(obs.source == "web_crawl" for obs in detail.observations)

    iphone = next(item for item in products if item.node.canonical_name == "iPhone 17 Pro")
    iphone_detail = manager.get_product(iphone.node.id)
    assert iphone_detail is not None
    assert iphone_detail.brand and iphone_detail.brand.canonical_name == "Apple"
    assert iphone_detail.brand.description == "Apple designs iPhone hardware and software products."
    assert iphone_detail.owner and iphone_detail.owner.canonical_name == "Apple Inc."
    assert iphone_detail.brand.status == "candidate"
    web_vlm_observations = [
        obs
        for obs in iphone_detail.observations
        if obs.source == "web_vlm" and obs.field == "web_vlm_product_fact"
    ]
    assert len(web_vlm_observations) == 1
    assert iphone_detail.category is None
    assert any(obs.field == "web_vlm_category_hint" for obs in iphone_detail.observations)

    with manager.graph.connect(readonly=True) as conn:
        source = conn.execute(
            """
            SELECT source_type, payload_json
            FROM entity_sources
            WHERE source_type = 'discovery_only' AND url LIKE '%ford.example%'
            LIMIT 1
            """
        ).fetchone()
    assert source is not None
    assert source["source_type"] == "discovery_only"
    assert '"write_mode": "candidate_only"' in source["payload_json"]
    assert '"vlm_result"' in source["payload_json"]

    suggestions = manager.list_ad_change_suggestions(status="pending", ad_id="ad_ford_trucks")
    assert suggestions
    iphone_suggestions = manager.list_ad_change_suggestions(
        status="pending",
        ad_id="ad_tmobile_iphone",
    )
    assert not any(item.field_path == "ads.brand_name" for item in iphone_suggestions)
    suggestion = suggestions[0]
    assert suggestion.field_path == "ads.subcategory"
    with pytest.raises(PermissionError):
        manager.apply_ad_change_suggestion(suggestion.id)
    approved = manager.approve_ad_change_suggestion(suggestion.id)
    assert approved.status == "approved"
    applied = manager.apply_ad_change_suggestion(suggestion.id, value="pickup truck")
    assert applied.status == "applied"

    readonly = open_readonly_database(submitted_db)
    try:
        row = readonly.execute(
            "SELECT subcategory FROM ads WHERE id = ?",
            ("ad_ford_trucks",),
        ).fetchone()
        assert row["subcategory"] == "pickup truck"
    finally:
        readonly.close()


def test_crawl_queue_product_edit_and_ingest_assist(config_path: Path) -> None:
    create_app(config_path=config_path)
    _seed_noisy_products(config_path)
    _seed_publisher_overlay_target(config_path)
    submitted_db, graph_db = _paths(config_path)
    crawler_config_path = _write_entity_crawler_config(config_path)
    manager = EntityGraphManager(
        graph_db,
        submitted_db,
        crawler_config_path=crawler_config_path,
    )
    manager.run_resolver(limit=10)

    queue = manager.crawl_queue(limit=10)
    by_ad = {item.ad_id: item for item in queue}
    assert by_ad["ad_ford_trucks"].product_count >= 3
    assert by_ad["ad_ford_trucks"].has_web_targets is True
    assert by_ad["ad_tmobile_iphone"].has_web_targets is False
    assert by_ad["ad_wbal_overlay"].has_web_targets is False
    assert not any(
        target.ad_id == "ad_wbal_overlay"
        for target in manager.submitted_ads.list_web_targets(
            limit=20,
            ad_ids=["ad_wbal_overlay"],
        )
    )

    products = manager.list_products(limit=20)
    iphone = next(item for item in products if item.node.canonical_name == "iPhone 17 Pro")
    updated = manager.update_product(
        iphone.node.id,
        brand_name="Apple",
        owner_name="Apple Inc.",
        category_name="smartphone",
        status="confirmed_reviewed",
        confidence=0.96,
        brand_name_provided=True,
        owner_name_provided=True,
        category_name_provided=True,
    )
    assert updated.node.status == "confirmed_reviewed"
    assert updated.brand and updated.brand.canonical_name == "Apple"
    assert updated.owner and updated.owner.canonical_name == "Apple Inc."
    assert updated.category and updated.category.canonical_name == "smartphone"

    preview = manager.ingest_assist_preview(
        IngestAssistRequest(
            mode="crawl_reinforce",
            products=["iPhone 17 Pro"],
            brand_name="Apple",
            category_name="smartphone",
        )
    )
    assert preview.mode == "crawl_reinforce"
    assert preview.product_candidates
    assert preview.brand_candidates


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
    assert payload["category"]["canonical_name"] == "IAB Product 1028: Sport Utility Vehicles"
    assert len(payload["taxonomy_mappings"]) == 3
    assert payload["related_ads"][0]["ad_id"] == "ad_wrangle"

    queue = client.get("/api/entity-graph/crawler/queue", params={"limit": 10})
    assert queue.status_code == 200, queue.text
    assert any(item["ad_id"] == "ad_wrangle" for item in queue.json()["items"])

    patched = client.patch(
        f"/api/entity-graph/products/{wrangler['node']['id']}",
        json={
            "brand_name": "Jeep",
            "owner_name": "Stellantis N.V.",
            "category_name": "Sport Utility Vehicles",
            "confidence": 0.95,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["owner"]["canonical_name"] == "Stellantis N.V."

    ingest_preview = client.post(
        "/api/entity-graph/ingest-assist/preview",
        json={
            "mode": "use_graph",
            "products": ["Wrangler"],
            "brand_name": "Jeep",
            "category_name": "Sport Utility Vehicles",
        },
    )
    assert ingest_preview.status_code == 200, ingest_preview.text
    assert ingest_preview.json()["product_candidates"]

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

    reset = client.post("/api/entity-graph/reset")
    assert reset.status_code == 200
    assert reset.json() == {"reset": True}


def test_entity_graph_cli_resolves_and_reports_status(config_path: Path) -> None:
    create_app(config_path=config_path)
    _seed_ads(config_path)
    runner = CliRunner()

    resolved = runner.invoke(
        cli_app,
        ["entity-graph", "resolve", "--config", str(config_path), "--limit", "10"],
    )
    assert resolved.exit_code == 0, resolved.output
    assert '"product_name": "Wrangler"' in resolved.output

    status = runner.invoke(
        cli_app,
        ["entity-graph", "status", "--config", str(config_path)],
    )
    assert status.exit_code == 0, status.output
    assert '"submitted_db_query_only": true' in status.output
    assert '"Wrangler"' in status.output

    refused = runner.invoke(cli_app, ["entity-graph", "reset", "--config", str(config_path)])
    assert refused.exit_code == 1
    assert "Refusing to reset without --yes" in refused.output
