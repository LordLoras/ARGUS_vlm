from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.db.repositories.campaigns import AdCampaignRepository, CampaignRepository
from ad_classifier.models.campaigns import AdCampaignRecord, CampaignRecord


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    c = open_database(db)
    apply_migrations(c)
    c.execute(
        "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, ?)",
        ("ad_1", "/tmp/ad_1.mp4", datetime.now(UTC).isoformat()),
    )
    c.execute(
        "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, ?)",
        ("ad_2", "/tmp/ad_2.mp4", datetime.now(UTC).isoformat()),
    )
    c.commit()
    return c


def test_campaign_crud(conn):
    repo = CampaignRepository(conn)
    repo.create(CampaignRecord(id="c_1", name="Launch", brand="Jeep", created_by="user"))
    conn.commit()

    result = repo.get("c_1")
    assert result is not None
    assert result.name == "Launch"
    assert result.created_by == "user"

    updated = repo.update("c_1", name="Launch Updated", theme="summer")
    conn.commit()
    assert updated is not None
    assert updated.name == "Launch Updated"
    assert updated.theme == "summer"

    assert repo.list(brand="Jeep")[-1].id == "c_1"
    repo.delete("c_1")
    conn.commit()
    assert repo.get("c_1") is None


def test_auto_upsert_does_not_overwrite_user_campaign(conn):
    repo = CampaignRepository(conn)
    repo.create(CampaignRecord(id="c_same", name="User Campaign", created_by="user"))
    conn.commit()

    inserted = repo.upsert_auto(
        CampaignRecord(id="c_same", name="Auto Campaign", brand="Jeep", created_by="auto")
    )
    conn.commit()

    assert inserted is False
    assert repo.get("c_same").name == "User Campaign"


def test_assignment_crud_and_cascade_on_ad_delete(conn):
    campaigns = CampaignRepository(conn)
    assignments = AdCampaignRepository(conn)
    campaigns.create(CampaignRecord(id="c_1", name="Launch", created_by="user"))
    assignments.assign(AdCampaignRecord(ad_id="ad_1", campaign_id="c_1", assigned_by="user"))
    conn.commit()

    assert assignments.has_user_assignment("ad_1") is True
    assert assignments.list_for_campaign("c_1")[0].ad_id == "ad_1"
    assert assignments.ads_with_user_assignments() == {"ad_1"}

    assignments.unassign("c_1", "ad_1")
    conn.commit()
    assert assignments.list_for_campaign("c_1") == []

    assignments.assign(AdCampaignRecord(ad_id="ad_2", campaign_id="c_1", assigned_by="user"))
    conn.execute("DELETE FROM ads WHERE id = ?", ("ad_2",))
    conn.commit()
    assert assignments.list_for_campaign("c_1") == []
