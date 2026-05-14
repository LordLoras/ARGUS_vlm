from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ad_classifier.api.deps import get_config, open_request_db
from ad_classifier.campaigns.discover import discover_campaigns
from ad_classifier.campaigns.research import campaign_detail, campaign_rollup
from ad_classifier.campaigns.suggestions import CampaignProposal, scan_campaign_proposals
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.db.repositories import AdCampaignRepository, CampaignRepository
from ad_classifier.models.campaigns import AdCampaignRecord, CampaignRecord
from ad_classifier.vectors.sqlite_vec import SqliteVecStore

router = APIRouter(tags=["campaigns"])


class CampaignCreate(BaseModel):
    id: str | None = None
    name: str
    advertiser: str | None = None
    brand: str | None = None
    theme: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None


class CampaignPatch(BaseModel):
    name: str | None = None
    advertiser: str | None = None
    brand: str | None = None
    theme: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None


class AssignAdsRequest(BaseModel):
    ad_ids: list[str]


class CampaignProposalInput(BaseModel):
    id: str
    name: str
    advertiser: str | None = None
    brand: str | None = None
    theme: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    description: str | None = None
    ad_ids: list[str]
    mean_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    ad_scores: dict[str, float] | None = None


class AcceptDiscoveryRequest(BaseModel):
    campaign_ids: list[str] | None = None
    proposals: list[CampaignProposalInput] | None = None


@router.get("/campaigns")
def list_campaigns(
    request: Request,
    brand: str | None = None,
    created_by: str | None = None,
    q: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        items = CampaignRepository(conn).list(
            brand=brand,
            created_by=created_by,
            q=q,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [campaign_rollup(conn, item) for item in items],
            "limit": limit,
            "offset": offset,
        }
    finally:
        conn.close()


@router.post("/campaigns")
def create_campaign(body: CampaignCreate, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        body_data = body.model_dump()
        campaign_id = body_data.pop("id") or _campaign_id(body.name, body.brand)
        if CampaignRepository(conn).get(campaign_id) is not None:
            raise HTTPException(status_code=409, detail="campaign id already exists")
        campaign = CampaignRecord(id=campaign_id, **body_data, created_by="user")
        CampaignRepository(conn).create(campaign)
        conn.commit()
        return campaign_rollup(conn, campaign)
    finally:
        conn.close()


@router.post("/campaigns/discover")
def discover(
    request: Request,
    persist: bool = Query(default=False),
) -> dict[str, Any]:
    config = get_config(request)
    conn = open_request_db(request)
    try:
        load_sqlite_vec(conn)
        store = SqliteVecStore(
            conn,
            text_dim=config.vector_store.text_dim,
            visual_dim=config.vector_store.visual_dim,
        )
        store.ensure_tables()
        if persist:
            result = discover_campaigns(conn, store, config=config.campaigns.discover)
            conn.commit()
            proposals = [_proposal_from_discovered(item) for item in result.discovered]
            return {
                **result.model_dump(mode="json"),
                "proposals": [proposal.model_dump(mode="json") for proposal in proposals],
            }

        result = scan_campaign_proposals(conn, store, config=config.campaigns.discover)
        return result.model_dump(mode="json")
    finally:
        conn.close()


@router.post("/campaigns/discover/accept")
def accept_discovered(body: AcceptDiscoveryRequest, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        repo = CampaignRepository(conn)
        assignment_repo = AdCampaignRepository(conn)
        accepted: list[dict[str, Any]] = []
        selected_ids = set(body.campaign_ids or [])

        if body.proposals:
            proposals = [
                proposal
                for proposal in body.proposals
                if not selected_ids or proposal.id in selected_ids
            ]
            for proposal in proposals:
                campaign = CampaignRecord(
                    id=proposal.id,
                    name=proposal.name,
                    advertiser=proposal.advertiser,
                    brand=proposal.brand,
                    theme=proposal.theme,
                    start_date=proposal.start_date,
                    end_date=proposal.end_date,
                    created_by="user",
                    description=proposal.description,
                )
                repo.upsert_user(campaign)
                for ad_id in proposal.ad_ids:
                    assignment_repo.assign(
                        AdCampaignRecord(
                            ad_id=ad_id,
                            campaign_id=proposal.id,
                            similarity_score=(
                                (proposal.ad_scores or {}).get(ad_id)
                                or proposal.mean_similarity
                            ),
                            assigned_by="user",
                        )
                    )
                accepted.append(campaign_rollup(conn, campaign))
        else:
            campaigns = repo.list(created_by="auto", limit=100)
            if selected_ids:
                campaigns = [campaign for campaign in campaigns if campaign.id in selected_ids]
            for campaign in campaigns:
                promoted = repo.promote_to_user(campaign.id)
                if promoted is not None:
                    accepted.append(campaign_rollup(conn, promoted))

        conn.commit()
        return {"accepted": accepted}
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        campaign = _resolve_campaign(conn, campaign_id)
        return campaign_detail(conn, campaign)
    finally:
        conn.close()


@router.patch("/campaigns/{campaign_id}")
def patch_campaign(campaign_id: str, body: CampaignPatch, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        repo = CampaignRepository(conn)
        current = _resolve_campaign(conn, campaign_id)
        patch = body.model_dump(exclude_unset=True)
        if "name" in patch and not (patch["name"] or "").strip():
            raise HTTPException(status_code=400, detail="campaign name cannot be empty")
        updated = repo.update(current.id, **patch)
        conn.commit()
        if updated is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        return campaign_rollup(conn, updated)
    finally:
        conn.close()


@router.delete("/campaigns/{campaign_id}")
def delete_campaign(campaign_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        campaign = _resolve_campaign(conn, campaign_id)
        CampaignRepository(conn).delete(campaign.id)
        conn.commit()
        return {"deleted": campaign.id}
    finally:
        conn.close()


@router.post("/campaigns/{campaign_id}/ads")
def assign_ads(campaign_id: str, body: AssignAdsRequest, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        campaign = _resolve_campaign(conn, campaign_id)
        missing = _missing_ads(conn, body.ad_ids)
        if missing:
            raise HTTPException(status_code=404, detail={"missing_ads": missing})
        repo = AdCampaignRepository(conn)
        repo.assign_many(campaign.id, body.ad_ids, assigned_by="user")
        conn.commit()
        return {"campaign_id": campaign.id, "assigned": body.ad_ids}
    finally:
        conn.close()


@router.delete("/campaigns/{campaign_id}/ads/{ad_id}")
def unassign_ad(campaign_id: str, ad_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        campaign = _resolve_campaign(conn, campaign_id)
        AdCampaignRepository(conn).unassign(campaign.id, ad_id)
        conn.commit()
        return {"campaign_id": campaign.id, "unassigned": ad_id}
    finally:
        conn.close()


def _resolve_campaign(conn, campaign_id_or_name: str) -> CampaignRecord:
    repo = CampaignRepository(conn)
    campaign = repo.get(campaign_id_or_name) or repo.get_by_name(campaign_id_or_name)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return campaign


def _missing_ads(conn, ad_ids: list[str]) -> list[str]:
    unique_ids = sorted(set(ad_ids))
    if not unique_ids:
        return []
    placeholders = ",".join("?" for _ in unique_ids)
    rows = conn.execute(
        f"SELECT id FROM ads WHERE id IN ({placeholders})",
        unique_ids,
    ).fetchall()
    found = {str(row["id"]) for row in rows}
    return [ad_id for ad_id in unique_ids if ad_id not in found]


def _proposal_from_discovered(item) -> CampaignProposal:
    campaign = item.campaign
    return CampaignProposal(
        id=campaign.id,
        name=campaign.name,
        advertiser=campaign.advertiser,
        brand=campaign.brand,
        theme=campaign.theme,
        start_date=campaign.start_date.isoformat() if campaign.start_date else None,
        end_date=campaign.end_date.isoformat() if campaign.end_date else None,
        description=campaign.description,
        ad_ids=item.ad_ids,
        mean_similarity=item.mean_similarity,
    )


def _campaign_id(name: str, brand: str | None) -> str:
    raw = "_".join(part for part in [brand, name] if part)
    slug = re.sub(r"[^a-z0-9]+", "_", raw.casefold()).strip("_") or "campaign"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"c_{slug}_{digest}"[:96]
