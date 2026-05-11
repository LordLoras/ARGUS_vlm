from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ad_classifier.config import AgentConfig
from ad_classifier.db.connection import (
    apply_migrations,
    open_database,
    open_readonly_database,
)
from ad_classifier.db.repositories import (
    AdCampaignRepository,
    AdRepository,
    CampaignRepository,
)
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.models.ads import AdRecord
from ad_classifier.models.campaigns import AdCampaignRecord, CampaignRecord
from ad_classifier.models.classification import ClassificationRecord
from ad_classifier.models.marketing import (
    BrandEntity,
    CTAEntity,
    MarketingEntities,
    OfferEntity,
    PriceEntity,
)


def _classification(ad_id: str, category: str) -> ClassificationRecord:
    return ClassificationRecord(
        ad_id=ad_id,
        primary_category=category,
        confidence=0.9,
        vlm_model="google/gemma-4-26b-a4b",
        vlm_prompt_version="v1",
        embedder_text_model="all-MiniLM-L6-v2",
        embedder_visual_model="siglip2-base",
        pipeline_version="test",
    )


def _seed_ads(conn: sqlite3.Connection) -> None:
    ads = AdRepository(conn)
    classifications = ClassificationRepository(conn)
    marketing = MarketingEntityRepository(conn)

    ads.upsert_ingest(
        AdRecord(
            id="ad_jeep_a",
            source_path="/tmp/jeep_a.mp4",
            status="completed",
            source_hash="hash_a",
        )
    )
    ads.update_projection(
        "ad_jeep_a",
        brand_name="Jeep",
        brand_confidence=0.95,
        advertiser_name="Stellantis",
        website_domain=None,
        phone_number=None,
        landing_page_domain=None,
        products_text="Wrangler",
        primary_category="automotive",
    )
    classifications.upsert(_classification("ad_jeep_a", "automotive"))
    marketing.upsert(
        "ad_jeep_a",
        MarketingEntities(
            brand=BrandEntity(name="Jeep"),
            products=["Wrangler"],
            prices=[PriceEntity(text="$30,000")],
            offers=[OfferEntity(text="0% APR for 60 months")],
            ctas=[CTAEntity(text="Visit your local dealer")],
        ),
    )

    ads.upsert_ingest(
        AdRecord(
            id="ad_jeep_b",
            source_path="/tmp/jeep_b.mp4",
            status="completed",
            source_hash="hash_b",
        )
    )
    ads.update_projection(
        "ad_jeep_b",
        brand_name="Jeep",
        brand_confidence=0.92,
        advertiser_name="Stellantis",
        website_domain=None,
        phone_number=None,
        landing_page_domain=None,
        products_text="Grand Cherokee",
        primary_category="automotive",
    )
    classifications.upsert(_classification("ad_jeep_b", "automotive"))
    marketing.upsert(
        "ad_jeep_b",
        MarketingEntities(
            brand=BrandEntity(name="Jeep"),
            products=["Grand Cherokee"],
            prices=[PriceEntity(text="$40,000")],
            offers=[OfferEntity(text="0% APR for 60 months")],
            ctas=[CTAEntity(text="Visit your local dealer")],
        ),
    )

    ads.upsert_ingest(
        AdRecord(
            id="ad_pizza_a",
            source_path="/tmp/pizza.mp4",
            status="completed",
            source_hash="hash_c",
        )
    )
    ads.update_projection(
        "ad_pizza_a",
        brand_name="Domino's",
        brand_confidence=0.99,
        advertiser_name="Domino's Pizza Inc",
        website_domain=None,
        phone_number=None,
        landing_page_domain=None,
        products_text="Large Pepperoni",
        primary_category="food_beverage",
    )
    classifications.upsert(_classification("ad_pizza_a", "food_beverage"))
    marketing.upsert(
        "ad_pizza_a",
        MarketingEntities(
            brand=BrandEntity(name="Domino's"),
            products=["Large Pepperoni"],
            prices=[PriceEntity(text="$9.99")],
            offers=[OfferEntity(text="2 for $19.99")],
            ctas=[CTAEntity(text="Order now")],
        ),
    )


def _seed_campaign(conn: sqlite3.Connection) -> None:
    repo = CampaignRepository(conn)
    repo.create(
        CampaignRecord(
            id="c_jeep_summer",
            name="Jeep Summer 2026",
            brand="Jeep",
            theme="summer",
            created_by="user",
            description="Summer Jeep promo",
            created_at=datetime.now(UTC),
        )
    )
    AdCampaignRepository(conn).assign(
        AdCampaignRecord(
            ad_id="ad_jeep_a",
            campaign_id="c_jeep_summer",
            assigned_by="user",
            assigned_at=datetime.now(UTC),
        )
    )


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    db = tmp_path / "agent.db"
    conn = open_database(db)
    apply_migrations(conn)
    _seed_ads(conn)
    _seed_campaign(conn)
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def writable_conn(db_path: Path):
    conn = open_database(db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def readonly_conn(db_path: Path):
    conn = open_readonly_database(db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def agent_config() -> AgentConfig:
    return AgentConfig()
