"""Read-only API surface for the intelligence crawler (usable as a standalone service).

Mirrors routes/entity_graph.py: a manager is held on ``app.state.intel_manager`` and
endpoints are thin. Read endpoints are the core; ``POST /crawl`` triggers a (bounded,
synchronous) crawl run for local/service use. Never leaks tracebacks.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ad_classifier.intelligence_crawler.manager import IntelManager
from ad_classifier.intelligence_crawler.timeutils import parse_iso, utcnow

router = APIRouter(tags=["intelligence"])


class CrawlPayload(BaseModel):
    due: bool = True
    source_id: str | None = None
    brand: str | None = None


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


@router.get("/intelligence/signals")
def list_signals(
    request: Request,
    brand: str | None = None,
    since: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    items = _manager(request).list_signals(
        brand=brand, since=_parse_since(since), status=status, limit=limit
    )
    return {"items": [item.model_dump(mode="json") for item in items], "limit": limit}


@router.get("/intelligence/signals/{signal_id}")
def get_signal(signal_id: str, request: Request) -> dict[str, Any]:
    signal = _manager(request).get_signal(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="signal not found")
    return signal.model_dump(mode="json")


@router.get("/intelligence/digest")
def get_digest(
    request: Request,
    since: str | None = Query(default="7d"),
) -> dict[str, Any]:
    entries = _manager(request).digest(since=_parse_since(since))
    return {"entries": [entry.model_dump(mode="json") for entry in entries]}


@router.get("/intelligence/watchlist")
def get_watchlist(request: Request) -> dict[str, Any]:
    brands = _manager(request).watchlist()
    return {"items": [brand.model_dump(mode="json") for brand in brands]}


@router.get("/intelligence/source-types")
def get_source_types(request: Request) -> dict[str, Any]:
    return {"source_types": _manager(request).source_types()}


@router.post("/intelligence/crawl")
def run_crawl(payload: CrawlPayload, request: Request) -> dict[str, Any]:
    summary = _manager(request).run_crawl(
        due=payload.due, source_id=payload.source_id, brand=payload.brand
    )
    return summary.model_dump(mode="json")
