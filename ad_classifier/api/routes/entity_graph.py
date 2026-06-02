from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ad_classifier.entity_graph.manager import EntityGraphManager
from ad_classifier.entity_graph.models import DiscoveryCandidateRequest, EntityStatus

router = APIRouter(tags=["entity-graph"])


class ResolverPayload(BaseModel):
    mode: str = "minimal_review"
    fully_automatic: bool = False
    limit: int = Field(default=1000, ge=1, le=10000)


class StatusPayload(BaseModel):
    status: EntityStatus = "confirmed_reviewed"


def _manager(request: Request) -> EntityGraphManager:
    manager = getattr(request.app.state, "entity_graph_manager", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="Entity graph manager not initialized")
    return manager


@router.get("/entity-graph/products")
def list_products(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items = _manager(request).list_products(status=status, q=q, limit=limit, offset=offset)
    return {"items": [item.model_dump(mode="json") for item in items], "limit": limit, "offset": offset}


@router.get("/entity-graph/products/{product_id}")
def get_product(product_id: str, request: Request) -> dict[str, Any]:
    product = _manager(request).get_product(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="product entity not found")
    return product.model_dump(mode="json")


@router.get("/entity-graph/graph")
def get_graph(
    request: Request,
    limit: int = Query(default=400, ge=1, le=2000),
) -> dict[str, Any]:
    return _manager(request).graph_payload(limit=limit).model_dump(mode="json")


@router.get("/entity-graph/taxonomy-mappings")
def get_taxonomy_mappings(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    items = _manager(request).taxonomy_mappings(limit=limit)
    return {"items": [item.model_dump(mode="json") for item in items], "limit": limit}


@router.get("/entity-graph/readonly-status")
def readonly_status(request: Request) -> dict[str, bool]:
    return {"submitted_db_query_only": _manager(request).submitted_db_is_readonly()}


@router.post("/entity-graph/resolver/preview")
def preview_resolver(request: Request, payload: ResolverPayload | None = None) -> dict[str, Any]:
    body = payload or ResolverPayload()
    result = _manager(request).preview_resolver(
        mode=body.mode, fully_automatic=body.fully_automatic, limit=body.limit
    )
    return result.model_dump(mode="json")


@router.post("/entity-graph/resolver/run")
def run_resolver(request: Request, payload: ResolverPayload | None = None) -> dict[str, Any]:
    body = payload or ResolverPayload()
    result = _manager(request).run_resolver(
        mode=body.mode, fully_automatic=body.fully_automatic, limit=body.limit
    )
    return result.model_dump(mode="json")


@router.post("/entity-graph/entities/{entity_id}/promote")
def promote_entity(entity_id: str, request: Request) -> dict[str, Any]:
    return _manager(request).set_status(entity_id, "confirmed_reviewed").model_dump(mode="json")


@router.post("/entity-graph/entities/{entity_id}/reject")
def reject_entity(entity_id: str, request: Request) -> dict[str, Any]:
    return _manager(request).set_status(entity_id, "rejected").model_dump(mode="json")


@router.post("/entity-graph/entities/{entity_id}/review")
def review_entity(entity_id: str, request: Request, payload: StatusPayload | None = None) -> dict[str, Any]:
    body = payload or StatusPayload()
    return _manager(request).set_status(entity_id, body.status).model_dump(mode="json")


@router.post("/entity-graph/discovery-candidates")
def add_discovery_candidate(
    request: Request, payload: DiscoveryCandidateRequest
) -> dict[str, Any]:
    return _manager(request).add_discovery_candidate(payload).model_dump(mode="json")
