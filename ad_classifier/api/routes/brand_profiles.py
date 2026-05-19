from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ad_classifier.api.deps import get_config, open_request_db
from ad_classifier.brand_profiles.matching import SearchContext
from ad_classifier.brand_profiles.wikimedia import (
    BrandProfileNotFoundError,
    WikimediaBrandProfileClient,
    normalize_profile_name,
)
from ad_classifier.db.repositories.ads import AdRepository
from ad_classifier.db.repositories.brand_profiles import BrandProfileRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.models.ads import utc_now

router = APIRouter(tags=["brand-profiles"])


class BrandProfileEnrichmentRequest(BaseModel):
    target: Literal["brand", "advertiser"] = "brand"
    force: bool = False
    query: str | None = None


@router.post("/ads/{ad_id}/brand-profile/enrich")
def enrich_brand_profile(
    ad_id: str,
    body: BrandProfileEnrichmentRequest,
    request: Request,
) -> dict[str, Any]:
    config = get_config(request)
    if not config.brand_profiles.enabled:
        raise HTTPException(status_code=403, detail="brand profile enrichment is disabled")

    conn = open_request_db(request)
    try:
        ad = AdRepository(conn).get(ad_id)
        if ad is None:
            raise HTTPException(status_code=404, detail="ad not found")
        marketing = MarketingEntityRepository(conn).get(ad_id)
        name = body.query or _target_name(body.target, ad, marketing)
        if not name:
            raise HTTPException(status_code=400, detail=f"{body.target} name is not available")

        normalized = normalize_profile_name(name)
        repo = BrandProfileRepository(conn)
        cached = repo.get(normalized)
        if cached is not None and not body.force and _cache_valid(cached):
            conn.commit()
            return {
                "target": body.target,
                "cached": True,
                "profile": cached.model_dump(mode="json"),
            }

        client = _brand_profile_client(request)
        search_context = SearchContext(
            category=ad.primary_category,
            subcategory=ad.subcategory,
            products=marketing.products[:3] if marketing else [],
            parent_company=(
                marketing.advertiser.parent_company if marketing else None
            ),
            advertiser_name=ad.advertiser_name
            or (marketing.advertiser.advertiser_name if marketing else None),
            website_domain=ad.website_domain or ad.landing_page_domain,
        )
        try:
            profile = client.fetch(name, context=search_context)
        except BrandProfileNotFoundError as exc:
            if body.force or cached is not None:
                repo.delete(normalized)
                conn.commit()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail="Wikimedia profile lookup failed") from exc

        repo.upsert(profile)
        conn.commit()
        return {
            "target": body.target,
            "cached": False,
            "profile": profile.model_dump(mode="json"),
        }
    finally:
        conn.close()


def _target_name(target: str, ad, marketing) -> str | None:
    if target == "advertiser":
        return (
            ad.advertiser_name
            or (marketing.advertiser.advertiser_name if marketing else None)
            or (marketing.advertiser.parent_company if marketing else None)
        )
    return ad.brand_name or (marketing.brand.name if marketing else None)


def _cache_valid(profile) -> bool:
    return profile.expires_at is None or profile.expires_at > utc_now()


def _brand_profile_client(request: Request) -> WikimediaBrandProfileClient:
    factory = getattr(request.app.state, "brand_profile_client_factory", None)
    config = get_config(request)
    if factory is not None:
        return factory(config)
    profile_config = config.brand_profiles
    return WikimediaBrandProfileClient(
        user_agent=profile_config.user_agent,
        timeout_s=profile_config.timeout_s,
        cache_days=profile_config.cache_days,
        max_candidates=profile_config.max_candidates,
        max_parent_depth=profile_config.max_parent_depth,
    )
