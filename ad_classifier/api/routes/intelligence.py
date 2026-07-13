"""Read-only API surface for the intelligence crawler (usable as a standalone service).

Mirrors routes/entity_graph.py: a manager is held on ``app.state.intel_manager`` and
endpoints are thin. Read endpoints are the core; ``POST /crawl`` triggers a (bounded,
synchronous) crawl run for local/service use. Never leaks tracebacks.
"""

from __future__ import annotations

import hmac
import os
import sqlite3
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ad_classifier.entity_graph.utils import digest, normalize_name
from ad_classifier.intelligence_crawler.contract import INTELLIGENCE_SCHEMA_VERSION
from ad_classifier.intelligence_crawler.exports import iter_resource_export
from ad_classifier.intelligence_crawler.manager import IntelManager
from ad_classifier.intelligence_crawler.models import IntelSource, Tier
from ad_classifier.intelligence_crawler.timeutils import parse_iso, utcnow

router = APIRouter(tags=["intelligence"])


class CrawlPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    due: bool = True
    source_id: str | None = None
    brand: str | None = None
    force: bool = False


class SourceCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    brand: str
    source_type: str
    tier: Tier | None = None
    url: str | None = None
    platform: str | None = None
    platform_id: str | None = None
    enabled: bool = False
    poll_interval_hours: float = Field(default=12.0, gt=0)
    config: dict = Field(default_factory=dict)


class SourceUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand: str | None = None
    source_type: str | None = None
    tier: Tier | None = None
    url: str | None = None
    platform: str | None = None
    platform_id: str | None = None
    enabled: bool | None = None
    poll_interval_hours: float | None = Field(default=None, gt=0)
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


def _require_mutation_key(request: Request) -> None:
    manager = _manager(request)
    env_name = manager.config.mutation_api_key_env
    expected = os.getenv(env_name) if env_name else None
    if not expected:  # local desktop default; set the env var when exposing middleware
        return
    supplied = request.headers.get("X-Intelligence-Key", "")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="missing or invalid intelligence API key")


def _idempotency_key(request: Request) -> str | None:
    value = request.headers.get("Idempotency-Key", "").strip()
    if len(value) > 200:
        raise HTTPException(
            status_code=400, detail="Idempotency-Key must be at most 200 characters"
        )
    return value or None


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


@router.get("/intelligence/adapters")
def get_adapters(request: Request) -> dict[str, Any]:
    adapters = _call_manager(lambda: _manager(request).adapters())
    return {"items": [adapter.model_dump(mode="json") for adapter in adapters]}


@router.get("/intelligence/brands")
def list_brands(
    request: Request,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    brands = _call_manager(lambda: _manager(request).list_brand_overviews(query=q, limit=limit))
    return {"items": [brand.model_dump(mode="json") for brand in brands], "limit": limit}


@router.get("/intelligence/resources")
def list_resources(
    request: Request,
    brand: str | None = None,
    source_id: str | None = None,
    include_backfill: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    cursor: str | None = None,
) -> dict[str, Any]:
    if cursor and offset:
        raise HTTPException(status_code=400, detail="cursor and non-zero offset cannot be combined")
    manager = _manager(request)
    try:
        resources, next_cursor = _call_manager(
            lambda: manager.list_resources_page(
                brand=brand,
                source_id=source_id,
                include_backfill=include_backfill,
                limit=limit,
                offset=offset,
                cursor=cursor,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    total = _call_manager(
        lambda: manager.count_resources(
            brand=brand, source_id=source_id, include_backfill=include_backfill
        )
    )
    return {
        "schema_version": INTELLIGENCE_SCHEMA_VERSION,
        "items": [resource.model_dump(mode="json") for resource in resources],
        "limit": limit,
        "offset": offset,
        "total": total,
        "next_offset": (
            None if cursor else offset + len(resources) if offset + len(resources) < total else None
        ),
        "next_cursor": next_cursor,
    }


@router.get("/intelligence/resources/changes")
def list_resource_changes(
    request: Request,
    since: str | None = Query(default="1d"),
    cursor: str | None = None,
    brand: str | None = None,
    source_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=250),
) -> dict[str, Any]:
    try:
        items, next_cursor = _call_manager(
            lambda: _manager(request).list_resource_changes(
                since=_parse_since(since),
                cursor=cursor,
                brand=brand,
                source_id=source_id,
                limit=limit,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "schema_version": INTELLIGENCE_SCHEMA_VERSION,
        "items": items,
        "limit": limit,
        "next_cursor": next_cursor,
    }


@router.get("/intelligence/resources/export")
def export_resources(
    request: Request,
    format: Literal["json", "jsonl"] = "json",
    brand: str | None = None,
    source_id: str | None = None,
    include_backfill: bool = Query(default=True),
) -> StreamingResponse:
    manager = _manager(request)
    media_type = "application/x-ndjson" if format == "jsonl" else "application/json"
    extension = "jsonl" if format == "jsonl" else "json"
    return StreamingResponse(
        iter_resource_export(
            manager,
            export_format=format,
            brand=brand,
            source_id=source_id,
            include_backfill=include_backfill,
        ),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="argus-latest-ads.{extension}"',
            "X-ARGUS-Schema-Version": INTELLIGENCE_SCHEMA_VERSION,
        },
    )


@router.get("/intelligence/resources/{resource_id}")
def get_resource(resource_id: str, request: Request) -> dict[str, Any]:
    resource = _call_manager(lambda: _manager(request).get_resource(resource_id))
    if resource is None:
        raise HTTPException(status_code=404, detail="resource not found")
    return resource.model_dump(mode="json")


@router.get("/intelligence/resources/{resource_id}/history")
def get_resource_history(
    resource_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=250),
) -> dict[str, Any]:
    manager = _manager(request)
    if _call_manager(lambda: manager.get_resource(resource_id)) is None:
        raise HTTPException(status_code=404, detail="resource not found")
    items = _call_manager(lambda: manager.resource_history(resource_id, limit=limit))
    return {"items": items, "limit": limit}


@router.get("/intelligence/resources/{resource_id}/screenshot")
def resource_screenshot(resource_id: str, request: Request) -> FileResponse:
    """Serve a resource's card screenshot (Meta cards) from the crawler cache."""
    path = _call_manager(lambda: _manager(request).resource_screenshot_path(resource_id))
    if path is None:
        raise HTTPException(status_code=404, detail="resource has no screenshot")
    return FileResponse(path)


@router.post("/intelligence/crawl")
def run_crawl(payload: CrawlPayload, request: Request) -> dict[str, Any]:
    _require_mutation_key(request)
    summary = _call_manager(
        lambda: _manager(request).run_crawl(
            due=payload.due,
            source_id=payload.source_id,
            brand=payload.brand,
            force=payload.force,
        )
    )
    return summary.model_dump(mode="json")


@router.post("/intelligence/crawl/queue", status_code=202)
def queue_crawl(payload: CrawlPayload, request: Request) -> dict[str, Any]:
    _require_mutation_key(request)
    manager = _manager(request)
    summary = _call_manager(
        lambda: manager.queue_crawl(
            due=payload.due,
            source_id=payload.source_id,
            brand=payload.brand,
            force=payload.force,
            idempotency_key=_idempotency_key(request),
        )
    )
    return summary.model_dump(mode="json")


@router.get("/intelligence/health")
def intelligence_health(request: Request) -> dict[str, Any]:
    return _call_manager(lambda: _manager(request).health())


@router.get("/intelligence/runs")
def list_runs(request: Request, limit: int = Query(default=50, ge=1, le=250)) -> dict[str, Any]:
    return {"items": _call_manager(lambda: _manager(request).list_runs(limit=limit))}


@router.get("/intelligence/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict[str, Any]:
    run = _call_manager(lambda: _manager(request).get_run(run_id))
    if run is None:
        raise HTTPException(status_code=404, detail="crawl run not found")
    return run


@router.post("/intelligence/runs/{run_id}/retry", status_code=202)
def retry_run(run_id: str, request: Request) -> dict[str, Any]:
    _require_mutation_key(request)
    summary = _call_manager(lambda: _manager(request).retry_run(run_id))
    if summary is None:
        raise HTTPException(status_code=404, detail="crawl run not found")
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


@router.get("/intelligence/source-statuses")
def list_source_statuses(request: Request, brand: str | None = None) -> dict[str, Any]:
    items = _call_manager(lambda: _manager(request).list_source_statuses(brand=brand))
    return {"items": [item.model_dump(mode="json") for item in items]}


@router.post("/intelligence/sources")
def create_source(payload: SourceCreatePayload, request: Request) -> dict[str, Any]:
    _require_mutation_key(request)
    manager = _manager(request)
    source = IntelSource(
        id=_new_source_id(payload),
        brand_name=payload.brand,
        source_type=payload.source_type,
        tier=payload.tier or manager.default_tier(payload.source_type),
        url=payload.url,
        platform=payload.platform,
        platform_id=payload.platform_id,
        enabled=payload.enabled,
        poll_interval_hours=payload.poll_interval_hours,
        config=payload.config,
    )
    return _call_manager(lambda: manager.upsert_source(source)).model_dump(mode="json")


@router.patch("/intelligence/sources/{source_id}")
def update_source(source_id: str, payload: SourceUpdatePayload, request: Request) -> dict[str, Any]:
    _require_mutation_key(request)
    manager = _manager(request)
    existing = _call_manager(lambda: manager.get_source(source_id))
    if existing is None:
        raise HTTPException(status_code=404, detail="source not found")
    updates = payload.model_dump(exclude_unset=True)
    if "brand" in updates:
        updates["brand_name"] = updates.pop("brand")
    if "source_type" in updates and "tier" not in updates:
        updates["tier"] = manager.default_tier(str(updates["source_type"]))
    merged = existing.model_copy(update=updates)
    return _call_manager(lambda: manager.upsert_source(merged)).model_dump(mode="json")


@router.delete("/intelligence/sources/{source_id}")
def delete_source(source_id: str, request: Request) -> dict[str, Any]:
    _require_mutation_key(request)
    if not _call_manager(lambda: _manager(request).delete_source(source_id)):
        raise HTTPException(status_code=404, detail="source not found")
    return {"archived": source_id}


@router.get("/intelligence/sources/{source_id}/status")
def get_source_status(
    source_id: str,
    request: Request,
    run_limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    status = _call_manager(
        lambda: _manager(request).get_source_status(source_id, run_limit=run_limit)
    )
    if status is None:
        raise HTTPException(status_code=404, detail="source not found")
    return status.model_dump(mode="json")


@router.post("/intelligence/sources/{source_id}/crawl")
def crawl_source(
    source_id: str, request: Request, force: bool = Query(default=False)
) -> dict[str, Any]:
    _require_mutation_key(request)
    summary = _call_manager(lambda: _manager(request).run_crawl(source_id=source_id, force=force))
    return summary.model_dump(mode="json")


@router.post("/intelligence/sources/{source_id}/crawl/queue", status_code=202)
def queue_source_crawl(
    source_id: str,
    request: Request,
    force: bool = Query(default=False),
) -> dict[str, Any]:
    _require_mutation_key(request)
    manager = _manager(request)
    if _call_manager(lambda: manager.get_source(source_id)) is None:
        raise HTTPException(status_code=404, detail="source not found")
    summary = _call_manager(
        lambda: manager.queue_crawl(
            source_id=source_id,
            force=force,
            idempotency_key=_idempotency_key(request),
        )
    )
    return summary.model_dump(mode="json")
