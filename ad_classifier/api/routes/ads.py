from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from ad_classifier.api.deps import get_config, get_config_file, get_upload_probe, open_request_db
from ad_classifier.brand_profiles.wikimedia import normalize_profile_name
from ad_classifier.config import resolve_config_path
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.db.repositories import AdCampaignRepository, AdRepository, JobRepository
from ad_classifier.db.repositories.brand_profiles import BrandProfileRepository
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.dedup.file_hash import source_sha256
from ad_classifier.iab_content_taxonomy import iab_content_category_from_id
from ad_classifier.iab_taxonomy import iab_category_from_id
from ad_classifier.ingest.service import ad_id_from_source_hash
from ad_classifier.knowledge.runtime import content_categories_from_ids, product_category_from_id
from ad_classifier.models.ads import AdRecord
from ad_classifier.models.iab import IABCategory, IABContentCategory
from ad_classifier.models.jobs import JobRecord
from ad_classifier.search.fts import fts_delete
from ad_classifier.vectors.sqlite_vec import SqliteVecStore

router = APIRouter(tags=["ads"])
logger = structlog.get_logger(__name__)


class AdPatch(BaseModel):
    brand_name: str | None = None
    brand_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    advertiser_name: str | None = None
    website_domain: str | None = None
    phone_number: str | None = None
    landing_page_domain: str | None = None
    products_text: str | None = None
    primary_category: str | None = None
    subcategory: str | None = None
    iab_product_id: str | None = None
    iab_content_ids: list[str] | None = None
    tagline: str | None = None
    offers: list[dict[str, str | None]] | None = None
    ctas: list[dict[str, str | None]] | None = None


@router.post("/ads/upload")
async def upload_ad(
    request: Request,
    file: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    config = get_config(request)
    config_file = get_config_file(request)
    content_type = file.content_type or "application/octet-stream"
    if content_type not in set(config.api.upload.allowed_mime):
        raise HTTPException(status_code=415, detail=f"unsupported media type: {content_type}")

    upload_root = resolve_config_path(config.paths.uploads, config_file)
    upload_root.mkdir(parents=True, exist_ok=True)
    temp_path = upload_root / f"upload_{uuid.uuid4().hex}.tmp"
    total = 0
    try:
        with temp_path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > config.api.upload.max_bytes:
                    raise HTTPException(status_code=413, detail="upload too large")
                out.write(chunk)

        probe = get_upload_probe(request)
        try:
            probe(temp_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="uploaded video is not decodable") from exc

        file_hash = source_sha256(temp_path)
        ad_id = ad_id_from_source_hash(file_hash)
        suffix = _safe_suffix(file.filename)
        final_path = upload_root / f"{ad_id}{suffix}"

        conn = open_request_db(request)
        try:
            ads = AdRepository(conn)
            existing = ads.find_by_source_hash(file_hash)
            if existing is not None and config.dedup.skip_on_exact:
                conn.commit()
                return {
                    "ad_id": existing.id,
                    "job_id": None,
                    "state": "duplicate",
                    "duplicate_of": existing.id,
                }

            if temp_path.resolve() != final_path.resolve():
                if final_path.exists():
                    final_path.unlink()
                temp_path.replace(final_path)
            ads.upsert_ingest(
                AdRecord(
                    id=ad_id,
                    source_path=str(final_path),
                    status="new",
                    source_hash=file_hash,
                )
            )
            job_id = f"job_{uuid.uuid4().hex[:12]}"
            JobRepository(conn).create(
                JobRecord(
                    id=job_id,
                    ad_id=ad_id,
                    state="queued",
                    progress=0.0,
                    message="uploaded",
                )
            )
            conn.commit()
            return {"ad_id": ad_id, "job_id": job_id, "state": "queued"}
        finally:
            conn.close()
    finally:
        if temp_path.exists():
            temp_path.unlink()


@router.get("/ads")
def list_ads(
    request: Request,
    brand: str | None = None,
    category: str | None = None,
    risk_label: str | None = None,
    iab_unique_id: str | None = None,
    iab_tier_1: str | None = None,
    iab_content_id: str | None = None,
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
            iab_unique_id=iab_unique_id,
            iab_tier_1=iab_tier_1,
            iab_content_id=iab_content_id,
            status=status,
            q=q,
            limit=limit,
            offset=offset,
        )
        return {"items": [_dump(ad) for ad in ads], "limit": limit, "offset": offset}
    finally:
        conn.close()


@router.get("/ads/{ad_id}")
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
        brand_profile = _cached_profile(
            profile_repo,
            ad.brand_name or (marketing.brand.name if marketing else None),
        )
        advertiser_profile = _cached_profile(
            profile_repo,
            ad.advertiser_name or (marketing.advertiser.advertiser_name if marketing else None),
        )
        return {
            "ad": _dump(ad),
            "classification": _dump(classification),
            "marketing_entities": _dump(marketing),
            "campaigns": [_dump(campaign) for campaign in campaigns],
            "brand_profile": _dump(brand_profile),
            "advertiser_profile": _dump(advertiser_profile),
        }
    finally:
        conn.close()


@router.get("/ads/{ad_id}/frames")
def get_frames(ad_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        rows = conn.execute(
            "SELECT * FROM frames WHERE ad_id = ? ORDER BY frame_index",
            (ad_id,),
        ).fetchall()
        return {"items": [dict(row) for row in rows]}
    finally:
        conn.close()


@router.get("/ads/{ad_id}/evidence")
def get_evidence(ad_id: str, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        classification = ClassificationRepository(conn).get(ad_id)
        rule_rows = conn.execute(
            "SELECT * FROM rule_triggers WHERE ad_id = ? ORDER BY time_ms, id",
            (ad_id,),
        ).fetchall()
        if classification is None and not rule_rows:
            raise HTTPException(status_code=404, detail="evidence not found")
        return {
            "classification_evidence": (
                [_dump(item) for item in classification.evidence] if classification else []
            ),
            "rule_triggers": [dict(row) for row in rule_rows],
        }
    finally:
        conn.close()


@router.get("/ads/{ad_id}/similar")
def get_similar(
    ad_id: str, request: Request, k: int = Query(default=5, ge=1, le=50)
) -> dict[str, Any]:
    from ad_classifier.dedup.similarity import enrich_related_ads

    config = get_config(request)
    conn = open_request_db(request)
    try:
        store = SqliteVecStore(
            conn,
            text_dim=config.vector_store.text_dim,
            visual_dim=config.vector_store.visual_dim,
        )
        load_sqlite_vec(conn)
        store.ensure_tables()
        related = enrich_related_ads(
            store,
            ad_id,
            text_vector=store.get_text(ad_id),
            visual_vector=store.get_visual(ad_id),
            k=k,
            min_score=0.7,
        )
        return related.model_dump(mode="json")
    finally:
        conn.close()


@router.patch("/ads/{ad_id}")
def patch_ad(ad_id: str, patch: AdPatch, request: Request) -> dict[str, Any]:
    conn = open_request_db(request)
    try:
        repo = AdRepository(conn)
        current = repo.get(ad_id)
        if current is None:
            raise HTTPException(status_code=404, detail="ad not found")
        classification = ClassificationRepository(conn).get(ad_id)
        iab_product_set = "iab_product_id" in patch.model_fields_set
        iab_content_set = "iab_content_ids" in patch.model_fields_set
        iab_category = _resolve_iab_product_patch(
            request,
            patch.iab_product_id if iab_product_set else None,
            current=current,
            classification=classification,
            field_was_set=iab_product_set,
        )
        iab_content_categories = _resolve_iab_content_patch(
            request,
            patch.iab_content_ids if iab_content_set else None,
            current=current,
            classification=classification,
            field_was_set=iab_content_set,
        )
        repo.update_projection(
            ad_id,
            brand_name=patch.brand_name if patch.brand_name is not None else current.brand_name,
            brand_confidence=(
                patch.brand_confidence
                if patch.brand_confidence is not None
                else current.brand_confidence
            ),
            advertiser_name=(
                patch.advertiser_name
                if patch.advertiser_name is not None
                else current.advertiser_name
            ),
            website_domain=(
                patch.website_domain if patch.website_domain is not None else current.website_domain
            ),
            phone_number=(
                patch.phone_number if patch.phone_number is not None else current.phone_number
            ),
            landing_page_domain=(
                patch.landing_page_domain
                if patch.landing_page_domain is not None
                else current.landing_page_domain
            ),
            products_text=(
                patch.products_text if patch.products_text is not None else current.products_text
            ),
            primary_category=(
                patch.primary_category
                if patch.primary_category is not None
                else current.primary_category
            ),
            subcategory=(
                patch.subcategory if patch.subcategory is not None else current.subcategory
            ),
            iab_unique_id=iab_category.iab_unique_id if iab_category else None,
            iab_parent_id=iab_category.iab_parent_id if iab_category else None,
            iab_tier_1=iab_category.tier_1 if iab_category else None,
            iab_tier_2=iab_category.tier_2 if iab_category else None,
            iab_tier_3=iab_category.tier_3 if iab_category else None,
            iab_selected_depth=iab_category.selected_depth if iab_category else None,
            iab_selected_category=iab_category.selected_category if iab_category else None,
            iab_full_path=iab_category.full_path if iab_category else None,
            iab_confidence=iab_category.confidence if iab_category else None,
            iab_content_ids=",".join(item.iab_unique_id for item in iab_content_categories)
            or None,
            iab_content_paths=" | ".join(item.full_path for item in iab_content_categories)
            or None,
            iab_content_categories_json=(
                json.dumps([item.model_dump() for item in iab_content_categories])
                if iab_content_categories
                else None
            ),
        )
        _update_classification_projection(
            conn,
            ad_id,
            patch=patch,
            iab_product_set=iab_product_set,
            iab_content_set=iab_content_set,
            iab_category=iab_category,
            iab_content_categories=iab_content_categories,
        )

        marketing_repo = MarketingEntityRepository(conn)
        marketing = marketing_repo.get(ad_id)
        if marketing is not None:
            dirty = False
            if patch.tagline is not None:
                marketing.brand.tagline = patch.tagline or None
                dirty = True
            if patch.offers is not None:
                from ad_classifier.models.marketing import OfferEntity

                marketing.offers = []
                for o in patch.offers:
                    if o.get("text"):
                        existing = next(
                            (e for e in (marketing.offers or []) if e.text == o["text"]),
                            None,
                        )
                        evidence = existing.evidence if existing else []
                        marketing.offers.append(OfferEntity(text=o["text"], evidence=evidence))
                dirty = True
            if patch.ctas is not None:
                from ad_classifier.models.marketing import CTAEntity

                marketing.ctas = []
                for c in patch.ctas:
                    if c.get("text"):
                        existing = next(
                            (e for e in (marketing.ctas or []) if e.text == c["text"]),
                            None,
                        )
                        evidence = existing.evidence if existing else []
                        marketing.ctas.append(CTAEntity(text=c["text"], evidence=evidence))
                dirty = True
            if dirty:
                marketing_repo.upsert(ad_id, marketing)

        conn.commit()
        updated = repo.get(ad_id)

        # Record corrections in knowledge base
        _record_corrections(
            request,
            ad_id,
            current,
            patch,
            iab_product_set=iab_product_set,
            iab_content_set=iab_content_set,
        )

        return _dump(updated)
    finally:
        conn.close()


@router.delete("/ads/{ad_id}")
def delete_ad(
    ad_id: str,
    request: Request,
    cleanup_artifacts: bool = Query(default=False),
) -> dict[str, Any]:
    config = get_config(request)
    config_file = get_config_file(request)
    conn = open_request_db(request)
    try:
        ad = AdRepository(conn).get(ad_id)
        if ad is None:
            raise HTTPException(status_code=404, detail="ad not found")
        fts_delete(conn, ad_id)
        load_sqlite_vec(conn)
        store = SqliteVecStore(
            conn,
            text_dim=config.vector_store.text_dim,
            visual_dim=config.vector_store.visual_dim,
        )
        store.ensure_tables()
        store.delete(ad_id)
        AdRepository(conn).delete(ad_id)
        conn.commit()
    finally:
        conn.close()

    removed: list[str] = []
    if cleanup_artifacts:
        removed = _cleanup_artifacts(config, config_file, ad_id, ad.source_path)
    return {"deleted": ad_id, "artifacts_removed": removed}


def _cleanup_artifacts(config, config_file: Path, ad_id: str, source_path: str) -> list[str]:
    roots = [
        resolve_config_path(config.paths.uploads, config_file),
        resolve_config_path(config.paths.frames, config_file),
        resolve_config_path(config.paths.audio, config_file),
        resolve_config_path(config.paths.whisper, config_file),
        resolve_config_path(config.paths.out, config_file),
    ]
    targets = [
        roots[1] / ad_id,
        roots[2] / ad_id,
        roots[3] / ad_id,
        roots[4] / ad_id,
        Path(source_path),
    ]
    removed: list[str] = []
    for target in targets:
        resolved = target.expanduser().resolve()
        if not any(_is_relative_to(resolved, root.expanduser().resolve()) for root in roots):
            continue
        if resolved.is_dir():
            shutil.rmtree(resolved)
            removed.append(str(resolved))
        elif resolved.exists():
            resolved.unlink()
            removed.append(str(resolved))
    return removed


def _safe_suffix(filename: str | None) -> str:
    suffix = Path(filename or "upload.mp4").suffix.lower()
    return suffix if suffix in {".mp4", ".mov", ".webm"} else ".mp4"


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _dump(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _cached_profile(repo: BrandProfileRepository, name: str | None):
    if not name:
        return None
    normalized = normalize_profile_name(name)
    return repo.get(normalized) if normalized else None


def _resolve_iab_product_patch(
    request: Request,
    value: str | None,
    *,
    current: AdRecord,
    classification,
    field_was_set: bool,
) -> IABCategory | None:
    if not field_was_set:
        if classification and classification.iab_category:
            return classification.iab_category
        return _iab_category_from_ad(current)
    if not value:
        return None
    kb = getattr(request.app.state, "knowledge_manager", None)
    if kb is not None:
        category = product_category_from_id(kb, value, confidence="high")
        if category is not None:
            return category
    return iab_category_from_id(value, confidence="high")


def _resolve_iab_content_patch(
    request: Request,
    value: list[str] | None,
    *,
    current: AdRecord,
    classification,
    field_was_set: bool,
) -> list[IABContentCategory]:
    if not field_was_set:
        if classification and classification.iab_content_categories:
            return classification.iab_content_categories
        return _iab_content_categories_from_ad(current)
    if not value:
        return []
    ids = [item.strip() for item in value if item and item.strip()]
    kb = getattr(request.app.state, "knowledge_manager", None)
    if kb is not None:
        categories = content_categories_from_ids(
            kb,
            ids,
            confidence="high",
            reason="Manual taxonomy edit",
        )
        if categories:
            return categories
    return [
        category
        for unique_id in ids
        if (
            category := iab_content_category_from_id(
                unique_id,
                confidence="high",
                reason="Manual taxonomy edit",
            )
        )
        is not None
    ]


def _iab_category_from_ad(ad: AdRecord) -> IABCategory | None:
    if ad.iab_unique_id and (category := iab_category_from_id(ad.iab_unique_id, confidence=ad.iab_confidence or "unknown")):
        return category
    if not ad.iab_unique_id or not ad.iab_selected_category or not ad.iab_full_path:
        return None
    return IABCategory(
        iab_unique_id=ad.iab_unique_id,
        iab_parent_id=ad.iab_parent_id,
        tier_1=ad.iab_tier_1,
        tier_2=ad.iab_tier_2,
        tier_3=ad.iab_tier_3,
        selected_depth=ad.iab_selected_depth or 1,
        selected_category=ad.iab_selected_category,
        full_path=ad.iab_full_path,
        confidence=ad.iab_confidence or "unknown",
    )


def _iab_content_categories_from_ad(ad: AdRecord) -> list[IABContentCategory]:
    if ad.iab_content_categories_json:
        try:
            raw = json.loads(ad.iab_content_categories_json)
        except json.JSONDecodeError:
            raw = []
        if isinstance(raw, list):
            parsed = [
                IABContentCategory.model_validate(item)
                for item in raw
                if isinstance(item, dict)
            ]
            if parsed:
                return parsed
    ids = [item.strip() for item in (ad.iab_content_ids or "").split(",") if item.strip()]
    return [
        category
        for unique_id in ids
        if (category := iab_content_category_from_id(unique_id)) is not None
    ]


def _update_classification_projection(
    conn,
    ad_id: str,
    *,
    patch: AdPatch,
    iab_product_set: bool,
    iab_content_set: bool,
    iab_category: IABCategory | None,
    iab_content_categories: list[IABContentCategory],
) -> None:
    updates: dict[str, Any] = {}
    if patch.primary_category is not None:
        updates["primary_category"] = patch.primary_category
    if iab_product_set:
        updates["iab_category_json"] = (
            json.dumps(iab_category.model_dump()) if iab_category else None
        )
    if iab_content_set:
        updates["iab_content_categories_json"] = json.dumps(
            [item.model_dump() for item in iab_content_categories]
        )
    if not updates:
        return
    set_clause = ", ".join(f"{field} = ?" for field in updates)
    conn.execute(
        f"UPDATE classifications SET {set_clause} WHERE ad_id = ?",
        (*updates.values(), ad_id),
    )


def _record_corrections(
    request: Request,
    ad_id: str,
    current: AdRecord,
    patch: AdPatch,
    *,
    iab_product_set: bool = False,
    iab_content_set: bool = False,
) -> None:
    """Record field-level corrections in the knowledge base for learning."""
    kb = getattr(request.app.state, "knowledge_manager", None)
    if kb is None:
        return

    corrections: list[tuple[str, str | None, str | None]] = []

    if patch.primary_category is not None and patch.primary_category != current.primary_category:
        corrections.append(("primary_category", current.primary_category, patch.primary_category))

    if patch.subcategory is not None and patch.subcategory != current.subcategory:
        corrections.append(("subcategory", current.subcategory, patch.subcategory))

    if patch.brand_name is not None and patch.brand_name != current.brand_name:
        corrections.append(("brand_name", current.brand_name, patch.brand_name))

    if iab_product_set and patch.iab_product_id != current.iab_unique_id:
        corrections.append(("iab_product_id", current.iab_unique_id, patch.iab_product_id))

    if iab_content_set:
        new_content = ",".join(patch.iab_content_ids or [])
        if new_content != (current.iab_content_ids or ""):
            corrections.append(("iab_content_ids", current.iab_content_ids, new_content))

    brand = patch.brand_name or current.brand_name
    for field, old_val, new_val in corrections:
        from ad_classifier.knowledge.models import CorrectionEntry

        entry = CorrectionEntry(
            ad_id=ad_id,
            field=field,
            old_value=(
                brand
                if field in ("primary_category", "subcategory", "iab_product_id", "iab_content_ids")
                else old_val
            ),
            new_value=new_val,
            source="manual",
        )
        kb.record_correction(entry)
        if field in ("primary_category", "subcategory", "iab_product_id", "iab_content_ids"):
            kb.learn_from_correction(entry)
