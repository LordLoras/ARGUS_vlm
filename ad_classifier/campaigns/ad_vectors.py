from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from ad_classifier.campaigns.signals import CampaignSignal, campaign_suggestions_from_row
from ad_classifier.config import CampaignDiscoveryConfig
from ad_classifier.marketing.brand import brand_normalize
from ad_classifier.models.ads import utc_now


class VisualVectorLookup(Protocol):
    def get_visual(self, ad_id: str) -> list[float] | None: ...


@dataclass(frozen=True)
class AdVector:
    ad_id: str
    brand_key: str
    brand_display: str
    vector: list[float]
    ingested_at: datetime
    products: tuple[str, ...]
    offers: tuple[str, ...]
    campaign_suggestions: tuple[CampaignSignal, ...]


def load_ad_vectors(
    conn: sqlite3.Connection,
    store: VisualVectorLookup,
    config: CampaignDiscoveryConfig,
    user_assigned: set[str],
) -> tuple[list[AdVector], int]:
    cutoff = utc_now() - timedelta(days=config.lookback_days)
    rows = conn.execute(
        """
        SELECT
          ads.id,
          ads.brand_name,
          ads.products_text,
          ads.ingested_at,
          marketing_entities.products_json,
          marketing_entities.offers_json,
          marketing_entities.campaign_suggestions_json,
          marketing_entities.social_proof_json
        FROM ads
        LEFT JOIN marketing_entities ON marketing_entities.ad_id = ads.id
        WHERE ads.brand_name IS NOT NULL
          AND ads.brand_name <> ''
          AND ads.ingested_at >= ?
        ORDER BY lower(ads.brand_name), ads.ingested_at, ads.id
        """,
        (cutoff.isoformat(),),
    ).fetchall()

    ads: list[AdVector] = []
    missing_vectors = 0
    for row in rows:
        ad_id = str(row["id"])
        if ad_id in user_assigned:
            continue

        vector = store.get_visual(ad_id)
        if vector is None:
            missing_vectors += 1
            continue

        brand_display, brand_key = _brand_values(str(row["brand_name"]))
        ads.append(
            AdVector(
                ad_id=ad_id,
                brand_key=brand_key,
                brand_display=brand_display,
                vector=vector,
                ingested_at=_parse_datetime(row["ingested_at"]),
                products=tuple(_products_from_row(row)),
                offers=tuple(_offers_from_row(row)),
                campaign_suggestions=campaign_suggestions_from_row(row, brand_display, config),
            )
        )

    return ads, missing_vectors


def _brand_values(raw_brand: str) -> tuple[str, str]:
    normalized = brand_normalize(raw_brand) or raw_brand.strip()
    display = normalized.strip()
    return display, display.casefold()


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _products_from_row(row: sqlite3.Row) -> list[str]:
    products_json = row["products_json"]
    if products_json:
        try:
            values = json.loads(products_json)
            return [str(value).strip() for value in values if str(value).strip()]
        except json.JSONDecodeError:
            pass
    products_text = row["products_text"]
    if not products_text:
        return []
    return [part.strip() for part in str(products_text).split(",") if part.strip()]


def _offers_from_row(row: sqlite3.Row) -> list[str]:
    offers_json = row["offers_json"]
    if not offers_json:
        return []
    try:
        values = json.loads(offers_json)
    except json.JSONDecodeError:
        return []

    offers: list[str] = []
    for value in values:
        text = value.get("text") or value.get("value") if isinstance(value, dict) else value
        if text and str(text).strip():
            offers.append(str(text).strip())
    return offers
