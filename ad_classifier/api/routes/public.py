from __future__ import annotations

import json
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Request

from ad_classifier.api.deps import get_config, open_request_db
from ad_classifier.db.repositories import AdCampaignRepository, AdRepository
from ad_classifier.db.repositories.brand_profiles import BrandProfileRepository
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.models.ads import AdRecord

router = APIRouter(tags=["public"])
logger = structlog.get_logger(__name__)

_INTERNAL_AD_FIELDS = frozenset({
    "source_path",
    "source_hash",
    "phash_mean",
})

_INTERNAL_CLASSIFICATION_FIELDS = frozenset({
    "vlm_raw",
    "vlm_model",
    "vlm_prompt_version",
    "embedder_text_model",
    "embedder_visual_model",
    "pipeline_version",
})


@router.get("/public/ads")
def list_ads(
    request: Request,
    brand: str | None = None,
    category: str | None = None,
    risk_label: str | None = None,
    iab_tier_1: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        ads = AdRepository(conn).list(
            brand=brand,
            category=category,
            risk_label=risk_label,
            iab_tier_1=iab_tier_1,
            status=status or "completed",
            q=q,
            limit=limit,
            offset=offset,
        )
        items = []
        for ad in ads:
            row = _public_ad(ad)
            cls_repo = ClassificationRepository(conn)
            cls = cls_repo.get(ad.id)
            if cls is not None:
                row["primary_category"] = cls.primary_category
                row["risk_labels"] = cls.risk_labels
                row["confidence"] = cls.confidence
                row["sensitive_category"] = cls.sensitive_category
            items.append(row)
        return {"items": items, "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.get("/public/ads/{ad_id}")
def get_ad(ad_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        ad = AdRepository(conn).get(ad_id)
        if ad is None:
            raise HTTPException(status_code=404, detail="ad not found")

        classification = ClassificationRepository(conn).get(ad_id)
        try:
            marketing = MarketingEntityRepository(conn).get(ad_id)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("malformed_marketing_entities", ad_id=ad_id, error=str(exc))
            marketing = None
        campaigns = AdCampaignRepository(conn).list_for_ad(ad_id)
        profile_repo = BrandProfileRepository(conn)
        brand_name = ad.brand_name or (marketing.brand.name if marketing else None)
        brand_profile = _cached_profile(profile_repo, brand_name)
        advertiser_name = ad.advertiser_name or (
            marketing.advertiser.advertiser_name if marketing else None
        )
        advertiser_profile = _cached_profile(profile_repo, advertiser_name)

        frames = conn.execute(
            "SELECT frame_index, time_ms, width, height, kept, drop_reason FROM frames WHERE ad_id = ? ORDER BY frame_index",
            (ad_id,),
        ).fetchall()

        transcript_rows = conn.execute(
            "SELECT start_ms, end_ms, text, confidence FROM transcript_segments WHERE ad_id = ? ORDER BY start_ms",
            (ad_id,),
        ).fetchall()

        ocr_rows = conn.execute(
            """
            SELECT f.frame_index, f.time_ms, o.engine, o.text, o.confidence
            FROM frames f
            JOIN ocr_items o ON o.frame_id = f.id
            WHERE f.ad_id = ?
            ORDER BY f.frame_index, o.id
            """,
            (ad_id,),
        ).fetchall()

        rule_rows = conn.execute(
            "SELECT rule_id, category, risk_label, severity, evidence_text, time_ms, frame_index FROM rule_triggers WHERE ad_id = ? ORDER BY time_ms, id",
            (ad_id,),
        ).fetchall()

        return {
            "ad": _public_ad(ad),
            "classification": _public_classification(classification),
            "marketing_entities": _dump(marketing),
            "campaigns": [_dump(c) for c in campaigns],
            "brand_profile": _dump(brand_profile),
            "advertiser_profile": _dump(advertiser_profile),
            "frames": [dict(r) for r in frames],
            "transcript": {
                "segments": [dict(r) for r in transcript_rows],
                "full_text": " ".join(r["text"] for r in transcript_rows if r["text"]),
            },
            "ocr": [dict(r) for r in ocr_rows],
            "rule_triggers": [dict(r) for r in rule_rows],
        }
    finally:
        conn.close()


@router.get("/public/ads/{ad_id}/transcript")
def get_transcript(ad_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        _require_ad(conn, ad_id)
        rows = conn.execute(
            "SELECT start_ms, end_ms, text, confidence FROM transcript_segments WHERE ad_id = ? ORDER BY start_ms",
            (ad_id,),
        ).fetchall()
        items = [dict(r) for r in rows]
        return {
            "ad_id": ad_id,
            "segments": items,
            "full_text": " ".join(i["text"] for i in items if i.get("text")),
        }
    finally:
        conn.close()


@router.get("/public/ads/{ad_id}/ocr")
def get_ocr(ad_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        _require_ad(conn, ad_id)
        rows = conn.execute(
            """
            SELECT f.frame_index, f.time_ms, o.engine, o.text, o.confidence
            FROM frames f
            JOIN ocr_items o ON o.frame_id = f.id
            WHERE f.ad_id = ?
            ORDER BY f.frame_index, o.id
            """,
            (ad_id,),
        ).fetchall()
        return {"ad_id": ad_id, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/public/ads/{ad_id}/frames")
def get_frames(ad_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        _require_ad(conn, ad_id)
        rows = conn.execute(
            "SELECT frame_index, time_ms, width, height, kept, drop_reason FROM frames WHERE ad_id = ? ORDER BY frame_index",
            (ad_id,),
        ).fetchall()
        return {"ad_id": ad_id, "items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/public/stats")
def get_stats(
    request: Request,
    brand: str | None = None,
    category: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        where, params = _filters(brand=brand, category=category)
        total = conn.execute(f"SELECT COUNT(*) FROM ads WHERE status = 'completed' {where}", params).fetchone()[0]
        return {
            "total_ads": int(total),
            "by_category": _counts(conn, "primary_category", f"WHERE status = 'completed' {where}", params, limit),
            "by_brand": _counts(conn, "brand_name", f"WHERE status = 'completed' {where}", params, limit),
            "risk_labels": _risk_counts(conn, f"WHERE status = 'completed' {where}", params, limit),
        }
    finally:
        conn.close()


@router.get("/public/campaigns")
def list_campaigns(
    request: Request,
    brand: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    from ad_classifier.db.repositories.campaigns import CampaignRepository

    conn = open_request_db(request)
    try:
        repo = CampaignRepository(conn)
        campaigns = repo.list(brand=brand, limit=limit, offset=offset)
        return {
            "items": [_dump(c) for c in campaigns],
            "limit": limit,
            "offset": offset,
        }
    finally:
        conn.close()


@router.get("/public/campaigns/{campaign_id}")
def get_campaign(campaign_id: str, request: Request) -> dict[str, Any]:
    from ad_classifier.db.repositories.campaigns import CampaignRepository

    conn = open_request_db(request)
    try:
        repo = CampaignRepository(conn)
        campaign = repo.get(campaign_id)
        if campaign is None:
            raise HTTPException(status_code=404, detail="campaign not found")
        ad_repo = AdCampaignRepository(conn)
        assigned = ad_repo.list_for_campaign(campaign_id)
        return {
            "campaign": _dump(campaign),
            "ads": [_dump(a) for a in assigned],
        }
    finally:
        conn.close()


def _public_ad(ad: AdRecord) -> dict[str, Any]:
    data = ad.model_dump(mode="json")
    for field in _INTERNAL_AD_FIELDS:
        data.pop(field, None)
    return data


def _public_classification(cls: Any) -> dict[str, Any] | None:
    if cls is None:
        return None
    data = cls.model_dump(mode="json") if hasattr(cls, "model_dump") else dict(cls)
    for field in _INTERNAL_CLASSIFICATION_FIELDS:
        data.pop(field, None)
    return data


def _require_ad(conn, ad_id: str) -> AdRecord:
    ad = AdRepository(conn).get(ad_id)
    if ad is None:
        raise HTTPException(status_code=404, detail="ad not found")
    return ad


def _cached_profile(repo: BrandProfileRepository, name: str | None):
    if not name:
        return None
    from ad_classifier.brand_profiles.wikimedia import normalize_profile_name
    normalized = normalize_profile_name(name)
    return repo.get(normalized) if normalized else None


def _dump(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _filters(
    *,
    brand: str | None,
    category: str | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if brand:
        clauses.append("LOWER(brand_name) = LOWER(?)")
        params.append(brand)
    if category:
        clauses.append("primary_category = ?")
        params.append(category)
    return (f"AND {' AND '.join(clauses)}" if clauses else "", params)


def _counts(conn, column: str, where: str, params: list[Any], limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT {column} AS value, COUNT(*) AS count
        FROM ads
        {where}
        GROUP BY {column}
        ORDER BY count DESC, value IS NULL, value
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [{"value": row["value"], "count": int(row["count"])} for row in rows]


def _risk_counts(conn, where: str, params: list[Any], limit: int) -> list[dict[str, Any]]:
    join_where = where.replace("WHERE", "AND", 1) if where else ""
    rows = conn.execute(
        f"""
        SELECT json_each.value AS value, COUNT(*) AS count
        FROM classifications c
        JOIN ads ON ads.id = c.ad_id
        JOIN json_each(
          CASE
            WHEN json_valid(c.risk_labels_json) THEN c.risk_labels_json
            ELSE '[]'
          END
        )
        WHERE 1 = 1
        {join_where}
        GROUP BY json_each.value
        ORDER BY count DESC, value
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [{"value": row["value"], "count": int(row["count"])} for row in rows]
