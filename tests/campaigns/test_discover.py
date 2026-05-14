from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ad_classifier.campaigns.clustering import agglomerative_cluster_labels
from ad_classifier.campaigns.discover import discover_campaigns
from ad_classifier.campaigns.suggestions import scan_campaign_proposals
from ad_classifier.config import CampaignDiscoveryConfig
from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.db.repositories.campaigns import AdCampaignRepository, CampaignRepository
from ad_classifier.models.campaigns import AdCampaignRecord, CampaignRecord


class FakeVisualStore:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors

    def get_visual(self, ad_id: str) -> list[float] | None:
        return self.vectors.get(ad_id)


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "campaigns.db"
    c = open_database(db)
    apply_migrations(c)
    return c


def _insert_ad(
    conn: sqlite3.Connection,
    ad_id: str,
    *,
    brand: str,
    products: list[str] | None = None,
    offer: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO ads (id, source_path, ingested_at, brand_name, products_text)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            ad_id,
            f"/tmp/{ad_id}.mp4",
            datetime.now(UTC).isoformat(),
            brand,
            ", ".join(products or []),
        ),
    )
    conn.execute(
        """
        INSERT INTO marketing_entities (ad_id, products_json, offers_json)
        VALUES (?, ?, ?)
        """,
        (
            ad_id,
            json.dumps(products or []),
            json.dumps([{"text": offer}] if offer else []),
        ),
    )


def _discovery_config() -> CampaignDiscoveryConfig:
    return CampaignDiscoveryConfig(
        clusterer="agglomerative",
        lookback_days=365,
        min_cluster_size=3,
        min_mean_similarity=0.95,
    )


def test_agglomerative_clusters_close_vectors_only():
    labels = agglomerative_cluster_labels(
        [
            [1.0, 0.0],
            [0.999, 0.001],
            [0.998, 0.002],
            [0.0, 1.0],
        ],
        min_cluster_size=3,
        min_similarity=0.95,
    )

    assert labels[:3] == [0, 0, 0]
    assert labels[3] == -1


def test_discover_campaigns_groups_by_brand_and_persists(conn):
    for idx in range(3):
        _insert_ad(
            conn,
            f"ad_jeep_{idx}",
            brand="Jeep",
            products=["Wrangler"],
            offer="Freedom Days",
        )
    _insert_ad(conn, "ad_jeep_far", brand="Jeep", products=["Compass"])
    _insert_ad(conn, "ad_ford_close", brand="Ford", products=["Bronco"], offer="Freedom Days")
    conn.commit()

    store = FakeVisualStore(
        {
            "ad_jeep_0": [1.0, 0.0],
            "ad_jeep_1": [0.999, 0.001],
            "ad_jeep_2": [0.998, 0.002],
            "ad_jeep_far": [0.0, 1.0],
            "ad_ford_close": [1.0, 0.0],
        }
    )

    result = discover_campaigns(conn, store, config=_discovery_config())
    conn.commit()

    assert len(result.discovered) == 1
    discovered = result.discovered[0]
    assert discovered.campaign.brand == "Jeep"
    assert "Freedom Days" in discovered.campaign.name
    assert discovered.ad_ids == ["ad_jeep_0", "ad_jeep_1", "ad_jeep_2"]
    assert CampaignRepository(conn).get(discovered.campaign.id) is not None
    assigned = AdCampaignRepository(conn).list_for_campaign(discovered.campaign.id)
    assert {item.ad_id for item in assigned} == set(discovered.ad_ids)
    assert all(item.assigned_by == "auto" for item in assigned)


def test_user_assignments_are_shielded_from_auto_discovery(conn):
    for idx in range(4):
        _insert_ad(conn, f"ad_jeep_{idx}", brand="Jeep", products=["Wrangler"])
    campaigns = CampaignRepository(conn)
    assignments = AdCampaignRepository(conn)
    campaigns.create(CampaignRecord(id="c_user", name="User Pick", created_by="user"))
    assignments.assign(
        AdCampaignRecord(ad_id="ad_jeep_0", campaign_id="c_user", assigned_by="user")
    )
    conn.commit()

    store = FakeVisualStore(
        {
            "ad_jeep_0": [1.0, 0.0],
            "ad_jeep_1": [0.999, 0.001],
            "ad_jeep_2": [0.998, 0.002],
            "ad_jeep_3": [0.997, 0.003],
        }
    )

    result = discover_campaigns(conn, store, config=_discovery_config())
    conn.commit()

    assert result.skipped_user_assigned_ads == 1
    assert len(result.discovered) == 1
    assert "ad_jeep_0" not in result.discovered[0].ad_ids
    assert {item.campaign_id for item in assignments.list_for_ad("ad_jeep_0")} == {"c_user"}


def test_scan_campaign_proposals_does_not_persist(conn):
    for idx in range(3):
        _insert_ad(
            conn,
            f"ad_jeep_{idx}",
            brand="Jeep",
            products=["Wrangler"],
            offer="Freedom Days",
        )
    conn.commit()

    store = FakeVisualStore(
        {
            "ad_jeep_0": [1.0, 0.0],
            "ad_jeep_1": [0.999, 0.001],
            "ad_jeep_2": [0.998, 0.002],
        }
    )

    result = scan_campaign_proposals(conn, store, config=_discovery_config())

    assert len(result.proposals) == 1
    proposal = result.proposals[0]
    assert proposal.name.startswith("Jeep")
    assert proposal.ad_ids == ["ad_jeep_0", "ad_jeep_1", "ad_jeep_2"]
    assert CampaignRepository(conn).list() == []
    assert conn.execute("SELECT COUNT(*) FROM ad_campaigns").fetchone()[0] == 0
