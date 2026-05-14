from __future__ import annotations

import hashlib
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass

from ad_classifier.campaigns.ad_vectors import AdVector
from ad_classifier.campaigns.clustering import cluster_vectors, mean_pairwise_similarity
from ad_classifier.campaigns.signals import (
    signal_display_name,
    starts_with_brand,
    strip_brand_prefix,
)
from ad_classifier.config import CampaignDiscoveryConfig
from ad_classifier.dedup.similarity import cosine_similarity
from ad_classifier.models.campaigns import CampaignRecord


@dataclass(frozen=True)
class CampaignCandidate:
    campaign: CampaignRecord
    ads: tuple[AdVector, ...]
    mean_similarity: float


def campaign_candidates(
    conn: sqlite3.Connection,
    ads: list[AdVector],
    config: CampaignDiscoveryConfig,
) -> list[CampaignCandidate]:
    candidates: list[CampaignCandidate] = []
    seen_ad_sets: set[tuple[str, ...]] = set()

    for signal_key, cluster, mean_similarity in _campaign_signal_clusters(ads, config):
        ordered = tuple(_ordered_ads(cluster))
        ad_set = _candidate_ad_set(ordered)
        if ad_set in seen_ad_sets:
            continue
        seen_ad_sets.add(ad_set)
        candidates.append(
            CampaignCandidate(
                campaign=_campaign_from_signal_cluster(
                    conn,
                    list(ordered),
                    signal_key,
                    mean_similarity,
                ),
                ads=ordered,
                mean_similarity=mean_similarity,
            )
        )

    for cluster, mean_similarity in _visual_clusters(ads, config):
        ordered = tuple(_ordered_ads(cluster))
        ad_set = _candidate_ad_set(ordered)
        if ad_set in seen_ad_sets:
            continue
        seen_ad_sets.add(ad_set)
        candidates.append(
            CampaignCandidate(
                campaign=_campaign_from_cluster(conn, list(ordered), config, mean_similarity),
                ads=ordered,
                mean_similarity=mean_similarity,
            )
        )

    return sorted(candidates, key=lambda item: (item.campaign.brand or "", item.campaign.id))


def ad_cluster_similarity(ad: AdVector, cluster: list[AdVector]) -> float:
    others = [candidate for candidate in cluster if candidate.ad_id != ad.ad_id]
    if not others:
        return 1.0
    return sum(cosine_similarity(ad.vector, other.vector) for other in others) / len(others)


def _campaign_signal_clusters(
    ads: list[AdVector],
    config: CampaignDiscoveryConfig,
) -> list[tuple[str, list[AdVector], float]]:
    if not config.use_campaign_suggestions:
        return []

    grouped: dict[tuple[str, str], list[AdVector]] = defaultdict(list)
    for ad in ads:
        seen_keys: set[str] = set()
        for signal in ad.campaign_suggestions:
            if signal.key in seen_keys:
                continue
            grouped[(ad.brand_key, signal.key)].append(ad)
            seen_keys.add(signal.key)

    clusters: list[tuple[str, list[AdVector], float]] = []
    for (_brand_key, signal_key), cluster in grouped.items():
        if len(cluster) < config.min_cluster_size:
            continue
        mean_similarity = mean_pairwise_similarity([ad.vector for ad in cluster])
        if mean_similarity < config.min_mean_similarity:
            continue
        clusters.append((signal_key, cluster, mean_similarity))
    return sorted(
        clusters, key=lambda item: (item[1][0].brand_key, item[0], _candidate_ad_set(item[1]))
    )


def _visual_clusters(
    ads: list[AdVector],
    config: CampaignDiscoveryConfig,
) -> list[tuple[list[AdVector], float]]:
    by_brand: dict[str, list[AdVector]] = defaultdict(list)
    for ad in ads:
        by_brand[ad.brand_key].append(ad)

    clusters: list[tuple[list[AdVector], float]] = []
    for brand_ads in by_brand.values():
        if len(brand_ads) < config.min_cluster_size:
            continue
        labels = cluster_vectors([ad.vector for ad in brand_ads], config)
        for label in sorted({x for x in labels if x >= 0}):
            cluster = [
                ad for ad, ad_label in zip(brand_ads, labels, strict=True) if ad_label == label
            ]
            if len(cluster) < config.min_cluster_size:
                continue

            mean_similarity = mean_pairwise_similarity([ad.vector for ad in cluster])
            if mean_similarity < config.min_mean_similarity:
                continue
            clusters.append((cluster, mean_similarity))

    return sorted(clusters, key=lambda item: (item[0][0].brand_key, _candidate_ad_set(item[0])))


def _campaign_from_cluster(
    conn: sqlite3.Connection,
    cluster: list[AdVector],
    config: CampaignDiscoveryConfig,
    mean_similarity: float,
) -> CampaignRecord:
    ordered = _ordered_ads(cluster)
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


def _campaign_from_signal_cluster(
    conn: sqlite3.Connection,
    cluster: list[AdVector],
    signal_key: str,
    mean_similarity: float,
) -> CampaignRecord:
    ordered = _ordered_ads(cluster)
    brand = ordered[0].brand_display
    start_date = min(ad.ingested_at for ad in ordered).date()
    end_date = max(ad.ingested_at for ad in ordered).date()
    display_name = signal_display_name(ordered, signal_key)
    theme = strip_brand_prefix(display_name, brand) or display_name
    name = display_name
    if not starts_with_brand(display_name, brand):
        name = f"{brand} {display_name}".strip()
    products = _common_values([product for ad in ordered for product in ad.products], limit=5)
    common_offer = _most_common([offer for ad in ordered for offer in ad.offers])
    rules = _shared_rule_texts(conn, [ad.ad_id for ad in ordered])
    campaign_id = _campaign_id(brand, signal_key, ordered)

    description_parts = [
        f"Auto-discovered from {len(ordered)} ads sharing extracted campaign signal "
        f"{display_name!r} with mean visual similarity {mean_similarity:.2f}."
    ]
    if products:
        description_parts.append(f"Products: {', '.join(products)}.")
    if common_offer:
        description_parts.append(f"Common offer: {common_offer}.")
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


def _campaign_id(brand: str, theme: str, cluster: list[AdVector]) -> str:
    ad_hash = hashlib.sha1("|".join(ad.ad_id for ad in cluster).encode("utf-8")).hexdigest()[:8]
    return f"c_{_slug(brand)}_{_slug(theme)}_{ad_hash}"[:96]


def _ordered_ads(cluster: list[AdVector] | tuple[AdVector, ...]) -> list[AdVector]:
    return sorted(cluster, key=lambda ad: (ad.ingested_at, ad.ad_id))


def _candidate_ad_set(cluster: list[AdVector] | tuple[AdVector, ...]) -> tuple[str, ...]:
    return tuple(sorted(ad.ad_id for ad in cluster))


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug or "campaign"
