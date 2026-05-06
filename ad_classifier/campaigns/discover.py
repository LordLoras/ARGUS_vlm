from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import Field

from ad_classifier.campaigns.clustering import cluster_vectors, mean_pairwise_similarity
from ad_classifier.config import CampaignDiscoveryConfig
from ad_classifier.db.repositories.campaigns import AdCampaignRepository, CampaignRepository
from ad_classifier.dedup.similarity import cosine_similarity
from ad_classifier.marketing.brand import brand_normalize
from ad_classifier.models.ads import utc_now
from ad_classifier.models.campaigns import AdCampaignRecord, CampaignRecord
from ad_classifier.models.common import StrictModel


class VisualVectorLookup(Protocol):
    def get_visual(self, ad_id: str) -> list[float] | None: ...


class DiscoveredCampaign(StrictModel):
    campaign: CampaignRecord
    ad_ids: list[str]
    mean_similarity: float = Field(ge=0.0, le=1.0)


class CampaignDiscoveryRun(StrictModel):
    discovered: list[DiscoveredCampaign] = Field(default_factory=list)
    skipped_missing_vectors: int = 0
    skipped_user_assigned_ads: int = 0


@dataclass(frozen=True)
class _AdVector:
    ad_id: str
    brand_key: str
    brand_display: str
    vector: list[float]
    ingested_at: datetime
    products: tuple[str, ...]
    offers: tuple[str, ...]


def discover_campaigns(
    conn: sqlite3.Connection,
    store: VisualVectorLookup,
    *,
    config: CampaignDiscoveryConfig | None = None,
) -> CampaignDiscoveryRun:
    """Discover and persist auto campaigns from brand-grouped visual embeddings."""
    cfg = config or CampaignDiscoveryConfig()
    campaign_repo = CampaignRepository(conn)
    assignment_repo = AdCampaignRepository(conn)

    user_assigned = assignment_repo.ads_with_user_assignments()
    ads, missing_vectors = _load_ad_vectors(conn, store, cfg, user_assigned)
    by_brand: dict[str, list[_AdVector]] = defaultdict(list)
    for ad in ads:
        by_brand[ad.brand_key].append(ad)

    discovered: list[DiscoveredCampaign] = []
    for brand_ads in by_brand.values():
        if len(brand_ads) < cfg.min_cluster_size:
            continue
        labels = cluster_vectors([ad.vector for ad in brand_ads], cfg)
        for label in sorted({x for x in labels if x >= 0}):
            cluster = [
                ad for ad, ad_label in zip(brand_ads, labels, strict=True) if ad_label == label
            ]
            if len(cluster) < cfg.min_cluster_size:
                continue

            mean_similarity = mean_pairwise_similarity([ad.vector for ad in cluster])
            if mean_similarity < cfg.min_mean_similarity:
                continue

            campaign = _campaign_from_cluster(conn, cluster, cfg, mean_similarity)
            if not campaign_repo.upsert_auto(campaign):
                continue

            for ad in cluster:
                assignment_repo.assign(
                    AdCampaignRecord(
                        ad_id=ad.ad_id,
                        campaign_id=campaign.id,
                        similarity_score=round(_ad_cluster_similarity(ad, cluster), 4),
                        assigned_by="auto",
                    )
                )

            discovered.append(
                DiscoveredCampaign(
                    campaign=campaign,
                    ad_ids=[ad.ad_id for ad in cluster],
                    mean_similarity=round(mean_similarity, 4),
                )
            )

    discovered.sort(key=lambda item: (item.campaign.brand or "", item.campaign.id))
    return CampaignDiscoveryRun(
        discovered=discovered,
        skipped_missing_vectors=missing_vectors,
        skipped_user_assigned_ads=len(user_assigned),
    )


def _load_ad_vectors(
    conn: sqlite3.Connection,
    store: VisualVectorLookup,
    config: CampaignDiscoveryConfig,
    user_assigned: set[str],
) -> tuple[list[_AdVector], int]:
    cutoff = utc_now() - timedelta(days=config.lookback_days)
    rows = conn.execute(
        """
        SELECT
          ads.id,
          ads.brand_name,
          ads.products_text,
          ads.ingested_at,
          marketing_entities.products_json,
          marketing_entities.offers_json
        FROM ads
        LEFT JOIN marketing_entities ON marketing_entities.ad_id = ads.id
        WHERE ads.brand_name IS NOT NULL
          AND ads.brand_name <> ''
          AND ads.ingested_at >= ?
        ORDER BY lower(ads.brand_name), ads.ingested_at, ads.id
        """,
        (cutoff.isoformat(),),
    ).fetchall()

    ads: list[_AdVector] = []
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
            _AdVector(
                ad_id=ad_id,
                brand_key=brand_key,
                brand_display=brand_display,
                vector=vector,
                ingested_at=_parse_datetime(row["ingested_at"]),
                products=tuple(_products_from_row(row)),
                offers=tuple(_offers_from_row(row)),
            )
        )

    return ads, missing_vectors


def _campaign_from_cluster(
    conn: sqlite3.Connection,
    cluster: list[_AdVector],
    config: CampaignDiscoveryConfig,
    mean_similarity: float,
) -> CampaignRecord:
    ordered = sorted(cluster, key=lambda ad: (ad.ingested_at, ad.ad_id))
    brand = ordered[0].brand_display
    start_date = min(ad.ingested_at for ad in ordered).date()
    end_date = max(ad.ingested_at for ad in ordered).date()
    common_offer = _most_common([offer for ad in ordered for offer in ad.offers])
    products = _common_values([product for ad in ordered for product in ad.products], limit=5)
    rules = _shared_rule_texts(conn, [ad.ad_id for ad in ordered])
    theme = common_offer
    name = _campaign_name(brand, common_offer, start_date, config.name_template)
    campaign_id = _campaign_id(brand, common_offer or start_date.isoformat(), ordered)

    description_parts = [
        f"Auto-discovered from {len(ordered)} ads with mean visual similarity "
        f"{mean_similarity:.2f}."
    ]
    if products:
        description_parts.append(f"Products: {', '.join(products)}.")
    if common_offer:
        description_parts.append(f"Shared offer: {common_offer}.")
    if rules:
        description_parts.append(f"Shared signals: {', '.join(rules)}.")

    return CampaignRecord(
        id=campaign_id,
        name=name,
        brand=brand,
        theme=theme,
        start_date=start_date,
        end_date=end_date,
        created_by="auto",
        description=" ".join(description_parts),
    )


def _ad_cluster_similarity(ad: _AdVector, cluster: list[_AdVector]) -> float:
    others = [candidate for candidate in cluster if candidate.ad_id != ad.ad_id]
    if not others:
        return 1.0
    return sum(cosine_similarity(ad.vector, other.vector) for other in others) / len(others)


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


def _shared_rule_texts(conn: sqlite3.Connection, ad_ids: list[str]) -> list[str]:
    if not ad_ids:
        return []
    placeholders = ", ".join("?" for _ in ad_ids)
    rows = conn.execute(
        f"""
        SELECT evidence_text, rule_id
        FROM rule_triggers
        WHERE ad_id IN ({placeholders})
        """,
        ad_ids,
    ).fetchall()
    values = [str(row["evidence_text"] or row["rule_id"]) for row in rows]
    return _common_values(values, limit=5)


def _most_common(values: list[str]) -> str | None:
    common = _common_values(values, limit=1)
    return common[0] if common else None


def _common_values(values: list[str], *, limit: int) -> list[str]:
    normalized: dict[str, str] = {}
    counts: Counter[str] = Counter()
    for value in values:
        key = re.sub(r"\s+", " ", value).strip().casefold()
        if not key:
            continue
        normalized.setdefault(key, value.strip())
        counts[key] += 1
    return [normalized[key] for key, count in counts.most_common(limit) if count >= 2]


def _campaign_name(
    brand: str,
    common_offer: str | None,
    start_date: object,
    template: str,
) -> str:
    if common_offer:
        return f"{brand} {common_offer}"
    if hasattr(start_date, "strftime"):
        month = start_date.strftime("%B")
        year = start_date.strftime("%Y")
    else:
        month = ""
        year = ""
    return template.format(brand=brand, month=month, year=year).strip()


def _campaign_id(brand: str, theme: str, cluster: list[_AdVector]) -> str:
    ad_hash = hashlib.sha1("|".join(ad.ad_id for ad in cluster).encode("utf-8")).hexdigest()[:8]
    return f"c_{_slug(brand)}_{_slug(theme)}_{ad_hash}"[:96]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug or "campaign"
