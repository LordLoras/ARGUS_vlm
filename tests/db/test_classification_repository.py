from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.models.classification import ClassificationRecord
from ad_classifier.models.iab import IABCategory, IABContentCategory


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    c = open_database(db)
    apply_migrations(c)
    # Insert a parent ad row so FK constraint passes
    c.execute(
        "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, ?)",
        ("ad_test", "/tmp/x.mp4", "2026-01-01T00:00:00"),
    )
    c.commit()
    return c


def _record(ad_id: str = "ad_test") -> ClassificationRecord:
    return ClassificationRecord(
        ad_id=ad_id,
        primary_category="retail",
        risk_labels=[],
        confidence=0.88,
        vlm_model="argus/vlm",
        vlm_prompt_version="verifier-2026.05.01",
        embedder_text_model="all-MiniLM-L6-v2",
        embedder_visual_model="siglip2-base",
        pipeline_version="0.1.0",
    )


def test_upsert_and_get(conn):
    repo = ClassificationRepository(conn)
    record = _record()
    record.iab_category = IABCategory(
        iab_unique_id="1554",
        iab_parent_id="1553",
        tier_1="Vehicles",
        tier_2="Automotive Ownership",
        tier_3="New Vehicle Ownership",
        selected_depth=3,
        selected_category="New Vehicle Ownership",
        full_path="Vehicles > Automotive Ownership > New Vehicle Ownership",
        confidence="high",
    )
    record.iab_content_categories = [
        IABContentCategory(
            iab_unique_id="6",
            iab_parent_id="2",
            tier_1="Automotive",
            tier_2="Auto Body Styles",
            tier_3="SUV",
            selected_depth=3,
            selected_category="SUV",
            full_path="Automotive > Auto Body Styles > SUV",
            confidence="high",
            reason="SUV visible in on-screen text",
        )
    ]
    repo.upsert(record)
    conn.commit()

    result = repo.get("ad_test")
    assert result is not None
    assert result.ad_id == "ad_test"
    assert result.primary_category == "retail"
    assert result.iab_category is not None
    assert result.iab_category.iab_unique_id == "1554"
    assert (
        result.iab_category.full_path == "Vehicles > Automotive Ownership > New Vehicle Ownership"
    )
    assert len(result.iab_content_categories) == 1
    assert result.iab_content_categories[0].iab_unique_id == "6"
    assert result.iab_content_categories[0].full_path == "Automotive > Auto Body Styles > SUV"
    assert result.risk_labels == []


def test_upsert_overwrites(conn):
    repo = ClassificationRepository(conn)
    repo.upsert(_record())
    conn.commit()

    updated = _record()
    updated.primary_category = "gambling"
    repo.upsert(updated)
    conn.commit()

    result = repo.get("ad_test")
    assert result.primary_category == "gambling"


def test_get_nonexistent_returns_none(conn):
    repo = ClassificationRepository(conn)
    assert repo.get("nonexistent_id") is None


def test_delete(conn):
    repo = ClassificationRepository(conn)
    repo.upsert(_record())
    conn.commit()
    repo.delete("ad_test")
    conn.commit()
    assert repo.get("ad_test") is None
