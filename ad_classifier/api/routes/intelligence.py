"""Read-only API surface for the intelligence crawler (usable as a standalone service).

Mirrors routes/entity_graph.py: a manager is held on ``app.state.intel_manager`` and
endpoints are thin. Read endpoints are the core; ``POST /crawl`` triggers a (bounded,
synchronous) crawl run for local/service use. Never leaks tracebacks.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ad_classifier.entity_graph.utils import digest, normalize_name
from ad_classifier.intelligence_crawler.manager import IntelManager
from ad_classifier.intelligence_crawler.models import IntelSource, Tier
from ad_classifier.intelligence_crawler.timeutils import parse_iso, utcnow

router = APIRouter(tags=["intelligence"])


class CrawlPayload(BaseModel):
    due: bool = True
    source_id: str | None = None
    brand: str | None = None


class SourceCreatePayload(BaseModel):
    id: str | None = None
    brand: str
    source_type: str
    tier: Tier = "B"
    url: str | None = None
    platform: str | None = None
    platform_id: str | None = None
    enabled: bool = False
    poll_interval_hours: float = 12.0
    config: dict = {}


class SourceUpdatePayload(BaseModel):
    brand: str | None = None
    source_type: str | None = None
    tier: Tier | None = None
    url: str | None = None
    platform: str | None = None
    platform_id: str | None = None
    enabled: bool | None = None
    poll_interval_hours: float | None = None
    config: dict | None = None


def _new_source_id(payload: SourceCreatePayload) -> str:
    if payload.id:
        return payload.id
    base = normalize_name(payload.brand).replace(" ", "_") or "brand"
    suffix = digest(payload.source_type, payload.url or payload.platform_id or "")[:6]
    return f"{base}_{payload.source_type}_{suffix}"


def _manager(request: Request) -> IntelManager:
    manager = getattr(request.app.state, "intel_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Intelligence crawler not initialized")
    return manager


def _parse_since(value: str | None):
    if not value:
        return None
    text = value.strip().lower()
    if text.endswith("d") and text[:-1].isdigit():
        return utcnow() - timedelta(days=int(text[:-1]))
    return parse_iso(value)


def _call_manager(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise HTTPException(
                status_code=409,
                detail="intelligence crawler database is busy; retry after the current action finishes",
            ) from exc
        raise


@router.get("/intelligence/signals")
def list_signals(
    request: Request,
    brand: str | None = None,
    since: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    items = _call_manager(
        lambda: _manager(request).list_signals(
            brand=brand, since=_parse_since(since), status=status, limit=limit
        )
    )
    return {"items": [item.model_dump(mode="json") for item in items], "limit": limit}


@router.get("/intelligence/signals/{signal_id}")
def get_signal(signal_id: str, request: Request) -> dict[str, Any]:
    signal = _call_manager(lambda: _manager(request).get_signal(signal_id))
    if signal is None:
        raise HTTPException(status_code=404, detail="signal not found")
    return signal.model_dump(mode="json")


@router.get("/intelligence/digest")
def get_digest(
    request: Request,
    since: str | None = Query(default="7d"),
) -> dict[str, Any]:
    entries = _call_manager(lambda: _manager(request).digest(since=_parse_since(since)))
    return {"entries": [entry.model_dump(mode="json") for entry in entries]}


@router.get("/intelligence/watchlist")
def get_watchlist(request: Request) -> dict[str, Any]:
    brands = _call_manager(lambda: _manager(request).watchlist())
    return {"items": [brand.model_dump(mode="json") for brand in brands]}


@router.get("/intelligence/source-types")
def get_source_types(request: Request) -> dict[str, Any]:
    return {"source_types": _call_manager(lambda: _manager(request).source_types())}


@router.post("/intelligence/crawl")
def run_crawl(payload: CrawlPayload, request: Request) -> dict[str, Any]:
    summary = _call_manager(
        lambda: _manager(request).run_crawl(
            due=payload.due, source_id=payload.source_id, brand=payload.brand
        )
    )
    return summary.model_dump(mode="json")


# ---- source registry (the "Watcher" curation surface) -------------------------


@router.get("/intelligence/sources")
def list_sources(
    request: Request,
    brand: str | None = None,
    enabled_only: bool = Query(default=False),
) -> dict[str, Any]:
    items = _call_manager(
        lambda: _manager(request).list_sources(enabled_only=enabled_only, brand=brand)
    )
    return {"items": [source.model_dump(mode="json") for source in items]}


@router.post("/intelligence/sources")
def create_source(payload: SourceCreatePayload, request: Request) -> dict[str, Any]:
    source = IntelSource(
        id=_new_source_id(payload),
        brand_name=payload.brand,
        source_type=payload.source_type,
        tier=payload.tier,
        url=payload.url,
        platform=payload.platform,
        platform_id=payload.platform_id,
        enabled=payload.enabled,
        poll_interval_hours=payload.poll_interval_hours,
        config=payload.config,
    )
    return _call_manager(lambda: _manager(request).upsert_source(source)).model_dump(mode="json")


@router.patch("/intelligence/sources/{source_id}")
def update_source(source_id: str, payload: SourceUpdatePayload, request: Request) -> dict[str, Any]:
    manager = _manager(request)
    existing = _call_manager(lambda: manager.get_source(source_id))
    if existing is None:
        raise HTTPException(status_code=404, detail="source not found")
    updates = payload.model_dump(exclude_unset=True)
    if "brand" in updates:
        updates["brand_name"] = updates.pop("brand")
    merged = existing.model_copy(update=updates)
    return _call_manager(lambda: manager.upsert_source(merged)).model_dump(mode="json")


@router.delete("/intelligence/sources/{source_id}")
def delete_source(source_id: str, request: Request) -> dict[str, Any]:
    if not _call_manager(lambda: _manager(request).delete_source(source_id)):
        raise HTTPException(status_code=404, detail="source not found")
    return {"deleted": source_id}


@router.post("/intelligence/sources/{source_id}/crawl")
def crawl_source(source_id: str, request: Request) -> dict[str, Any]:
    summary = _call_manager(lambda: _manager(request).run_crawl(source_id=source_id))
    return summary.model_dump(mode="json")
