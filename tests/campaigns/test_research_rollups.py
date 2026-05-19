from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ad_classifier.campaigns.research import campaign_detail
from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.db.repositories.campaigns import AdCampaignRepository, CampaignRepository
from ad_classifier.models.campaigns import CampaignRecord


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    c = open_database(db)
    apply_migrations(c)
    return c


def test_campaign_detail_rolls_up_runtime_and_yearless_product_families(
    conn: sqlite3.Connection,
):
    now = datetime.now(UTC).isoformat()
    ads = [
        ("ad_ram_2025", 15_000, '["2025 Ram 1500"]'),
        ("ad_ram_2026", 14_800, '["2026 Ram 1500"]'),
        ("ad_wrangler", 30_000, '["Jeep Wrangler"]'),
    ]
    for ad_id, duration_ms, products_json in ads:
        conn.execute(
            """
            INSERT INTO ads (id, source_path, ingested_at, duration_ms)
            VALUES (?, ?, ?, ?)
            """,
            (ad_id, f"/tmp/{ad_id}.mp4", now, duration_ms),
        )
        conn.execute(
            "INSERT INTO marketing_entities (ad_id, products_json) VALUES (?, ?)",
            (ad_id, products_json),
        )

    campaigns = CampaignRepository(conn)
    assignments = AdCampaignRepository(conn)
    campaigns.create(CampaignRecord(id="c_truck", name="Truck Launch", created_by="user"))
    assignments.assign_many("c_truck", [ad_id for ad_id, _duration, _products in ads])
    conn.commit()

    campaign = campaigns.get("c_truck")
    assert campaign is not None
    detail = campaign_detail(conn, campaign)

    runtime_counts = {
        item["value"]: item["count"] for item in detail["research"]["creative"]["runtime_buckets"]
    }
    assert runtime_counts == {"15s": 2, "30s": 1}

    product_families = detail["research"]["messaging"]["product_families"]
    ram = next(item for item in product_families if item["value"] == "Ram 1500")
    assert ram["count"] == 2
    assert ram["ad_count"] == 2
    assert ram["total_duration_ms"] == 29_800
    assert {item["value"] for item in ram["variants"]} == {"2025 Ram 1500", "2026 Ram 1500"}
