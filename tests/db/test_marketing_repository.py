from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.models.marketing import (
    BrandEntity,
    ContactPoints,
    CreativeFormat,
    CTAEntity,
    LandingPageEntity,
    MarketingEntities,
    PhoneNumberEntity,
    WebsiteEntity,
)


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "test.db"
    c = open_database(db)
    apply_migrations(c)
    c.execute(
        "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, ?)",
        ("ad_me", "/tmp/x.mp4", "2026-01-01T00:00:00"),
    )
    c.commit()
    return c


def _entities() -> MarketingEntities:
    return MarketingEntities(
        brand=BrandEntity(name="TestBrand", logo_present=True),
        products=["Widget Pro", "Widget Lite"],
        ctas=[CTAEntity(text="Buy Now")],
        creative_format=CreativeFormat(aspect_ratio="16:9", has_voiceover=True),
        contact_points=ContactPoints(
            websites=[WebsiteEntity(url="https://example.com/deal", domain="example.com")],
            phone_numbers=[PhoneNumberEntity(raw="(555) 123-4567", normalized="+15551234567")],
        ),
        landing_page=LandingPageEntity(
            url="https://example.com/deal",
            domain="example.com",
            path="/deal",
        ),
    )


def test_upsert_and_get(conn):
    repo = MarketingEntityRepository(conn)
    repo.upsert("ad_me", _entities())
    conn.commit()

    result = repo.get("ad_me")
    assert result is not None
    assert result.brand.name == "TestBrand"
    assert result.brand.logo_present is True
    assert result.products == ["Widget Pro", "Widget Lite"]
    assert len(result.ctas) == 1
    assert result.ctas[0].text == "Buy Now"
    assert result.creative_format.aspect_ratio == "16:9"
    assert result.contact_points.websites[0].domain == "example.com"
    assert result.primary_phone_number == "+15551234567"
    assert result.landing_page.path == "/deal"


def test_upsert_overwrites(conn):
    repo = MarketingEntityRepository(conn)
    repo.upsert("ad_me", _entities())
    conn.commit()

    updated = _entities()
    updated.brand.name = "NewBrand"
    updated.products = ["NewProduct"]
    repo.upsert("ad_me", updated)
    conn.commit()

    result = repo.get("ad_me")
    assert result.brand.name == "NewBrand"
    assert result.products == ["NewProduct"]


def test_get_nonexistent_returns_none(conn):
    repo = MarketingEntityRepository(conn)
    assert repo.get("nonexistent") is None


def test_delete(conn):
    repo = MarketingEntityRepository(conn)
    repo.upsert("ad_me", _entities())
    conn.commit()
    repo.delete("ad_me")
    conn.commit()
    assert repo.get("ad_me") is None
