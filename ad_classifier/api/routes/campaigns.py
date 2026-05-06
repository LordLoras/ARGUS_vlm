from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ad_classifier.api.deps import get_config, open_request_db
from ad_classifier.campaigns.discover import discover_campaigns
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.db.repositories import AdCampaignRepository, CampaignRepository
from ad_classifier.models.campaigns import CampaignRecord
from ad_classifier.vectors.sqlite_vec import SqliteVecStore

router = APIRouter(tags=["campaigns"])


class CampaignCreate(BaseModel):
    id: str
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


class AcceptDiscoveryRequest(BaseModel):
    campaign_ids: list[str] | None = None


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
        return {"items": [_dump(item) for item in items], "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.post("/campaigns")
def create_campaign(body: CampaignCreate, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        campaign = CampaignRecord(**body.model_dump(), created_by="user")
        CampaignRepository(conn).create(campaign)
        conn.commit()
        return _dump(campaign)
    finally:
        conn.close()


@router.post("/campaigns/discover")
def discover(request: Request) -> dict[str, Any]:
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
        result = discover_campaigns(conn, store, config=config.campaigns.discover)
        conn.commit()
        return result.model_dump(mode="json")
    finally:
        conn.close()


@router.post("/campaigns/discover/accept")
def accept_discovered(body: AcceptDiscoveryRequest, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        repo = CampaignRepository(conn)
        campaigns = repo.list(created_by="auto", limit=100)
        if body.campaign_ids is not None:
            campaigns = [
                campaign for campaign in campaigns if campaign.id in set(body.campaign_ids)
            ]
        return {"accepted": [_dump(campaign) for campaign in campaigns]}
    finally:
        conn.close()


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        campaign = _resolve_campaign(conn, campaign_id)
        assignments = AdCampaignRepository(conn).list_for_campaign(campaign.id)
        return {"campaign": _dump(campaign), "ads": [_dump(item) for item in assignments]}
    finally:
        conn.close()


@router.patch("/campaigns/{campaign_id}")
def patch_campaign(campaign_id: str, body: CampaignPatch, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        repo = CampaignRepository(conn)
        current = _resolve_campaign(conn, campaign_id)
        updated = repo.update(current.id, **body.model_dump(exclude_unset=True))
        conn.commit()
        return _dump(updated)
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


def _dump(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value
