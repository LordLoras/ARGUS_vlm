from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import Protocol

from pydantic import Field

from ad_classifier.campaigns.clustering import cluster_vectors, mean_pairwise_similarity
from ad_classifier.campaigns.discover import (
    _ad_cluster_similarity,
    _campaign_from_cluster,
    _load_ad_vectors,
)
from ad_classifier.config import CampaignDiscoveryConfig
from ad_classifier.db.repositories.campaigns import AdCampaignRepository
from ad_classifier.models.common import StrictModel


class VisualVectorLookup(Protocol):
    def get_visual(self, ad_id: str) -> list[float] | None: ...


class CampaignProposal(StrictModel):
    id: str
    name: str
    advertiser: str | None = None
    brand: str | None = None
    theme: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    ad_ids: list[str]
    mean_similarity: float = Field(ge=0.0, le=1.0)
    ad_scores: dict[str, float] = Field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.ad_ids)


class CampaignSuggestionScan(StrictModel):
    proposals: list[CampaignProposal] = Field(default_factory=list)
    skipped_missing_vectors: int = 0
    skipped_user_assigned_ads: int = 0


def scan_campaign_proposals(
    conn: sqlite3.Connection,
    store: VisualVectorLookup,
    *,
    config: CampaignDiscoveryConfig | None = None,
) -> CampaignSuggestionScan:
    """Build reviewable campaign proposals without writing campaign rows."""
    cfg = config or CampaignDiscoveryConfig()
    user_assigned = AdCampaignRepository(conn).ads_with_user_assignments()
    ads, missing_vectors = _load_ad_vectors(conn, store, cfg, user_assigned)
    by_brand = defaultdict(list)
    for ad in ads:
        by_brand[ad.brand_key].append(ad)

    proposals: list[CampaignProposal] = []
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
            proposals.append(
                CampaignProposal(
                    id=campaign.id,
                    name=campaign.name,
                    advertiser=campaign.advertiser,
                    brand=campaign.brand,
                    theme=campaign.theme,
                    start_date=(
                        campaign.start_date.isoformat() if campaign.start_date else None
                    ),
                    end_date=campaign.end_date.isoformat() if campaign.end_date else None,
                    description=campaign.description,
                    ad_ids=[ad.ad_id for ad in cluster],
                    mean_similarity=round(mean_similarity, 4),
                    ad_scores={
                        ad.ad_id: round(_ad_cluster_similarity(ad, cluster), 4)
                        for ad in cluster
                    },
                )
            )

    proposals.sort(key=lambda item: (item.brand or "", item.id))
    return CampaignSuggestionScan(
        proposals=proposals,
        skipped_missing_vectors=missing_vectors,
        skipped_user_assigned_ads=len(user_assigned),
    )
