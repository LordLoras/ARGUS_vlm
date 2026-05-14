from __future__ import annotations

import sqlite3
from typing import Protocol

from pydantic import Field

from ad_classifier.campaigns.ad_vectors import load_ad_vectors
from ad_classifier.campaigns.candidates import ad_cluster_similarity, campaign_candidates
from ad_classifier.config import CampaignDiscoveryConfig
from ad_classifier.db.repositories.campaigns import AdCampaignRepository, CampaignRepository
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


def discover_campaigns(
    conn: sqlite3.Connection,
    store: VisualVectorLookup,
    *,
    config: CampaignDiscoveryConfig | None = None,
) -> CampaignDiscoveryRun:
    """Discover and persist auto campaigns from repeated signals and visual embeddings."""
    cfg = config or CampaignDiscoveryConfig()
    campaign_repo = CampaignRepository(conn)
    assignment_repo = AdCampaignRepository(conn)

    user_assigned = assignment_repo.ads_with_user_assignments()
    ads, missing_vectors = load_ad_vectors(conn, store, cfg, user_assigned)

    discovered: list[DiscoveredCampaign] = []
    for candidate in campaign_candidates(conn, ads, cfg):
        campaign = candidate.campaign
        cluster = list(candidate.ads)
        if not campaign_repo.upsert_auto(campaign):
            continue

        for ad in cluster:
            assignment_repo.assign(
                AdCampaignRecord(
                    ad_id=ad.ad_id,
                    campaign_id=campaign.id,
                    similarity_score=round(ad_cluster_similarity(ad, cluster), 4),
                    assigned_by="auto",
                )
            )

        discovered.append(
            DiscoveredCampaign(
                campaign=campaign,
                ad_ids=[ad.ad_id for ad in cluster],
                mean_similarity=round(candidate.mean_similarity, 4),
            )
        )

    discovered.sort(key=lambda item: (item.campaign.brand or "", item.campaign.id))
    return CampaignDiscoveryRun(
        discovered=discovered,
        skipped_missing_vectors=missing_vectors,
        skipped_user_assigned_ads=len(user_assigned),
    )
