from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ad_classifier.entity_graph.manager import EntityGraphManager
from ad_classifier.entity_graph.models import (
    AdChangeSuggestionStatus,
    DiscoveryCandidateRequest,
    EntityStatus,
    EntityType,
    IngestAssistRequest,
)

router = APIRouter(tags=["entity-graph"])


class ResolverPayload(BaseModel):
    mode: str = "minimal_review"
    fully_automatic: bool = False
    limit: int = Field(default=1000, ge=1, le=10000)


class CrawlerTargetPayload(BaseModel):
    ad_id: str
    url: str


class CrawlerPayload(BaseModel):
    limit: int = Field(default=100, ge=1, le=10000)
    ad_ids: list[str] = Field(default_factory=list, max_length=10000)
    targets: list[CrawlerTargetPayload] = Field(default_factory=list, max_length=2000)


class StatusPayload(BaseModel):
    status: EntityStatus = "confirmed_reviewed"


class ApplySuggestionPayload(BaseModel):
    value: str | None = None


class ProductUpdatePayload(BaseModel):
    canonical_name: str | None = None
    description: str | None = None
    status: EntityStatus | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    brand_name: str | None = None
    owner_name: str | None = None
    category_name: str | None = None


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


@router.get("/entity-graph/products/{product_id}/crawler-trace")
def get_product_crawler_trace(
    product_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    try:
        items = _manager(request).product_crawler_trace(product_id, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="product entity not found") from exc
    return {"items": [item.model_dump(mode="json") for item in items], "limit": limit}


@router.patch("/entity-graph/products/{product_id}")
def update_product(
    product_id: str,
    request: Request,
    payload: ProductUpdatePayload,
) -> dict[str, Any]:
    body = payload
    try:
        return _manager(request).update_product(
            product_id,
            canonical_name=body.canonical_name,
            description=body.description,
            status=body.status,
            confidence=body.confidence,
            brand_name=body.brand_name,
            owner_name=body.owner_name,
            category_name=body.category_name,
            brand_name_provided="brand_name" in body.model_fields_set,
            owner_name_provided="owner_name" in body.model_fields_set,
            category_name_provided="category_name" in body.model_fields_set,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="product entity not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/entity-graph/nodes/lookup")
def lookup_nodes(
    request: Request,
    entity_type: EntityType,
    q: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    items = _manager(request).lookup_nodes(entity_type=entity_type, q=q, limit=limit)
    return {"items": [item.model_dump(mode="json") for item in items], "limit": limit}


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


@router.post("/entity-graph/crawler/run")
def run_crawler(request: Request, payload: CrawlerPayload | None = None) -> dict[str, Any]:
    body = payload or CrawlerPayload()
    ad_ids = [item.strip() for item in body.ad_ids if item.strip()]
    target_urls: dict[str, list[str]] = {}
    for target in body.targets:
        ad_id = target.ad_id.strip()
        url = target.url.strip()
        if not ad_id or not url:
            continue
        target_urls.setdefault(ad_id, []).append(url)
    return _manager(request).run_crawler(
        limit=body.limit,
        ad_ids=ad_ids,
        target_urls=target_urls,
    ).model_dump(mode="json")


@router.get("/entity-graph/crawler/queue")
def crawl_queue(
    request: Request,
    q: str | None = None,
    limit: int = Query(default=1000, ge=1, le=10000),
) -> dict[str, Any]:
    items = _manager(request).crawl_queue(limit=limit, q=q)
    return {"items": [item.model_dump(mode="json") for item in items], "limit": limit}


@router.get("/entity-graph/ad-change-suggestions")
def list_ad_change_suggestions(
    request: Request,
    status: AdChangeSuggestionStatus | None = None,
    ad_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    items = _manager(request).list_ad_change_suggestions(
        status=status,
        ad_id=ad_id,
        limit=limit,
    )
    return {"items": [item.model_dump(mode="json") for item in items], "limit": limit}


@router.post("/entity-graph/ad-change-suggestions/{suggestion_id}/approve")
def approve_ad_change_suggestion(suggestion_id: str, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).approve_ad_change_suggestion(suggestion_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="ad change suggestion not found") from exc


@router.post("/entity-graph/ad-change-suggestions/{suggestion_id}/reject")
def reject_ad_change_suggestion(suggestion_id: str, request: Request) -> dict[str, Any]:
    try:
        return _manager(request).reject_ad_change_suggestion(suggestion_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="ad change suggestion not found") from exc


@router.post("/entity-graph/ad-change-suggestions/{suggestion_id}/apply")
def apply_ad_change_suggestion(
    suggestion_id: str,
    request: Request,
    payload: ApplySuggestionPayload | None = None,
) -> dict[str, Any]:
    body = payload or ApplySuggestionPayload()
    try:
        return _manager(request).apply_ad_change_suggestion(
            suggestion_id,
            value=body.value,
        ).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="ad change suggestion not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/entity-graph/reset")
def reset_graph(request: Request) -> dict[str, bool]:
    return _manager(request).reset_graph()


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


@router.post("/entity-graph/ingest-assist/preview")
def ingest_assist_preview(
    request: Request,
    payload: IngestAssistRequest,
) -> dict[str, Any]:
    return _manager(request).ingest_assist_preview(payload).model_dump(mode="json")
