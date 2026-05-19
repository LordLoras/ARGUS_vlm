"""Admin API for taxonomy management, brand rules, overrides, and corrections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ad_classifier.db.connection import open_database
from ad_classifier.knowledge.backfill import apply_suggestion, run_backfill_analysis
from ad_classifier.knowledge.manager import KnowledgeManager
from ad_classifier.knowledge.models import (
    BackfillSuggestion,
    BrandCategoryRule,
    CorrectionEntry,
    InferenceRule,
    TaxonomyOverride,
)

router = APIRouter(tags=["knowledge"])
logger = structlog.get_logger(__name__)


class BrandRulePayload(BaseModel):
    brand_name: str
    primary_category: str | None = None
    iab_product_id: str | None = None
    iab_content_ids: list[str] = Field(default_factory=list)
    subcategory: str | None = None
    source: str = "manual"
    confidence: float = 1.0
    priority: int = 0
    active: bool = True
    notes: str | None = None


class OverridePayload(BaseModel):
    override_type: str
    pattern: str
    primary_category: str | None = None
    iab_product_id: str | None = None
    iab_content_ids: list[str] = Field(default_factory=list)
    priority: int = 0
    active: bool = True
    notes: str | None = None


class InferenceRulePayload(BaseModel):
    taxonomy_type: str
    target_id: str
    terms: list[str]
    context_terms: list[str] = Field(default_factory=list)
    priority: int = 0
    active: bool = True
    notes: str | None = None


class CorrectionPayload(BaseModel):
    ad_id: str
    field: str
    old_value: str | None = None
    new_value: str | None = None
    source: str = "manual"
    learn: bool = True


class LoadTaxonomyPayload(BaseModel):
    product_tsv: str | None = None
    content_tsv: str | None = None


def _kb(request: Request) -> KnowledgeManager:
    kb = getattr(request.app.state, "knowledge_manager", None)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge manager not initialized")
    return kb


# ── Stats & Init ────────────────────────────────────────────


@router.get("/knowledge/stats")
def get_knowledge_stats(request: Request) -> dict[str, Any]:
    return _kb(request).get_stats()


@router.post("/knowledge/load-taxonomies")
def load_taxonomies(request: Request, payload: LoadTaxonomyPayload | None = None) -> dict[str, Any]:
    kb = _kb(request)
    product_tsv = Path(payload.product_tsv) if payload and payload.product_tsv else None
    content_tsv = Path(payload.content_tsv) if payload and payload.content_tsv else None
    kwargs: dict[str, Any] = {}
    if product_tsv:
        kwargs["product_tsv"] = product_tsv
    if content_tsv:
        kwargs["content_tsv"] = content_tsv
    return kb.load_taxonomies(**kwargs)


# ── Product Taxonomy ────────────────────────────────────────


@router.get("/knowledge/taxonomy/product")
def list_product_taxonomy(
    request: Request,
    parent_id: str | None = None,
    tier_1: str | None = None,
    active_only: bool = True,
    roots_only: bool = True,
) -> list[dict[str, Any]]:
    entries = _kb(request).list_product_taxonomy(
        parent_id=parent_id,
        tier_1=tier_1,
        active_only=active_only,
        roots_only=roots_only,
    )
    return [e.model_dump() for e in entries]


@router.get("/knowledge/taxonomy/product/{unique_id}")
def get_product_entry(request: Request, unique_id: str) -> dict[str, Any]:
    entry = _kb(request).get_product_entry(unique_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Product taxonomy entry not found")
    return entry.model_dump()


@router.get("/knowledge/taxonomy/product-search")
def search_product_taxonomy(
    request: Request, q: str = "", limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    if not q:
        return []
    entries = _kb(request).search_product_taxonomy(q, limit)
    return [e.model_dump() for e in entries]


@router.patch("/knowledge/taxonomy/product/{unique_id}/active")
def toggle_product_entry(request: Request, unique_id: str, active: bool = True) -> dict[str, Any]:
    ok = _kb(request).set_product_entry_active(unique_id, active)
    if not ok:
        raise HTTPException(status_code=404, detail="Product taxonomy entry not found")
    return {"unique_id": unique_id, "active": active}


# ── Content Taxonomy ────────────────────────────────────────


@router.get("/knowledge/taxonomy/content")
def list_content_taxonomy(
    request: Request,
    parent_id: str | None = None,
    tier_1: str | None = None,
    active_only: bool = True,
    roots_only: bool = True,
) -> list[dict[str, Any]]:
    entries = _kb(request).list_content_taxonomy(
        parent_id=parent_id,
        tier_1=tier_1,
        active_only=active_only,
        roots_only=roots_only,
    )
    return [e.model_dump() for e in entries]


@router.get("/knowledge/taxonomy/content/{unique_id}")
def get_content_entry(request: Request, unique_id: str) -> dict[str, Any]:
    entry = _kb(request).get_content_entry(unique_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Content taxonomy entry not found")
    return entry.model_dump()


@router.get("/knowledge/taxonomy/content-search")
def search_content_taxonomy(
    request: Request, q: str = "", limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    if not q:
        return []
    entries = _kb(request).search_content_taxonomy(q, limit)
    return [e.model_dump() for e in entries]


@router.patch("/knowledge/taxonomy/content/{unique_id}/active")
def toggle_content_entry(request: Request, unique_id: str, active: bool = True) -> dict[str, Any]:
    ok = _kb(request).set_content_entry_active(unique_id, active)
    if not ok:
        raise HTTPException(status_code=404, detail="Content taxonomy entry not found")
    return {"unique_id": unique_id, "active": active}


# ── Brand Rules ─────────────────────────────────────────────


@router.get("/knowledge/brand-rules")
def list_brand_rules(request: Request, active_only: bool = True) -> list[dict[str, Any]]:
    rules = _kb(request).list_brand_rules(active_only=active_only)
    return [r.model_dump() for r in rules]


@router.get("/knowledge/brand-rules/lookup")
def lookup_brand_rule(request: Request, brand: str) -> dict[str, Any] | None:
    rule = _kb(request).lookup_brand_rule(brand)
    return rule.model_dump() if rule else None


@router.post("/knowledge/brand-rules")
def create_brand_rule(request: Request, payload: BrandRulePayload) -> dict[str, Any]:
    rule = BrandCategoryRule(**payload.model_dump())
    result = _kb(request).upsert_brand_rule(rule)
    return result.model_dump()


@router.delete("/knowledge/brand-rules/{rule_id}")
def delete_brand_rule(request: Request, rule_id: int) -> dict[str, Any]:
    ok = _kb(request).delete_brand_rule(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Brand rule not found")
    return {"deleted": True}


# ── Overrides ───────────────────────────────────────────────


@router.get("/knowledge/overrides")
def list_overrides(request: Request, override_type: str | None = None) -> list[dict[str, Any]]:
    overrides = _kb(request).list_overrides(override_type=override_type)
    return [o.model_dump() for o in overrides]


@router.post("/knowledge/overrides")
def create_override(request: Request, payload: OverridePayload) -> dict[str, Any]:
    override = TaxonomyOverride(**payload.model_dump())
    result = _kb(request).upsert_override(override)
    return result.model_dump()


@router.delete("/knowledge/overrides/{override_id}")
def delete_override(request: Request, override_id: int) -> dict[str, Any]:
    ok = _kb(request).delete_override(override_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Override not found")
    return {"deleted": True}


# ── Inference Rules ─────────────────────────────────────────


@router.get("/knowledge/inference-rules")
def list_inference_rules(
    request: Request,
    taxonomy_type: str | None = None,
    active_only: bool = True,
) -> list[dict[str, Any]]:
    rules = _kb(request).list_inference_rules(taxonomy_type=taxonomy_type, active_only=active_only)
    return [r.model_dump() for r in rules]


@router.post("/knowledge/inference-rules")
def create_inference_rule(request: Request, payload: InferenceRulePayload) -> dict[str, Any]:
    rule = InferenceRule(**payload.model_dump())
    result = _kb(request).upsert_inference_rule(rule)
    return result.model_dump()


@router.delete("/knowledge/inference-rules/{rule_id}")
def delete_inference_rule(request: Request, rule_id: int) -> dict[str, Any]:
    ok = _kb(request).delete_inference_rule(rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Inference rule not found")
    return {"deleted": True}


# ── Corrections ─────────────────────────────────────────────


@router.get("/knowledge/corrections")
def list_corrections(
    request: Request, ad_id: str | None = None, limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    corrections = _kb(request).list_corrections(ad_id=ad_id, limit=limit)
    return [c.model_dump() for c in corrections]


@router.post("/knowledge/corrections")
def record_correction(request: Request, payload: CorrectionPayload) -> dict[str, Any]:
    kb = _kb(request)
    entry = CorrectionEntry(
        ad_id=payload.ad_id,
        field=payload.field,
        old_value=payload.old_value,
        new_value=payload.new_value,
        source=payload.source,
    )
    result = kb.record_correction(entry)

    if payload.learn:
        kb.learn_from_correction(entry)

    return result.model_dump()


# ── Backfill ────────────────────────────────────────────────


class BackfillApplyPayload(BaseModel):
    ad_id: str
    suggested_primary_category: str | None = None
    suggested_iab_product_id: str | None = None
    suggested_iab_content_ids: list[str] = Field(default_factory=list)
    brand_name: str | None = None
    rule_source: str | None = None
    confidence: float = 1.0


@router.post("/knowledge/backfill/analyze")
def run_backfill(
    request: Request,
    brand_rules_only: bool = True,
    limit: int = Query(default=1000, ge=1, le=10000),
) -> list[dict[str, Any]]:
    kb = _kb(request)
    db_path = request.app.state.db_path
    conn = open_database(db_path)
    try:
        suggestions = run_backfill_analysis(
            conn, kb, brand_rules_only=brand_rules_only, limit=limit,
        )
        return [s.model_dump() for s in suggestions]
    finally:
        conn.close()


@router.post("/knowledge/backfill/apply")
def apply_backfill(request: Request, payload: BackfillApplyPayload) -> dict[str, Any]:
    kb = _kb(request)
    db_path = request.app.state.db_path
    conn = open_database(db_path)
    try:
        suggestion = BackfillSuggestion(
            ad_id=payload.ad_id,
            brand_name=payload.brand_name,
            suggested_primary_category=payload.suggested_primary_category,
            suggested_iab_product_id=payload.suggested_iab_product_id,
            suggested_iab_content_ids=payload.suggested_iab_content_ids,
            rule_source=payload.rule_source,
            confidence=payload.confidence,
        )
        ok = apply_suggestion(conn, kb, suggestion)
        if not ok:
            raise HTTPException(status_code=400, detail="No applicable changes")
        return {"applied": True, "ad_id": payload.ad_id}
    finally:
        conn.close()
