"""SQLite row and JSON projection helpers for the intelligence repository."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ad_classifier.entity_graph.rows import loads_dict, loads_list, to_json
from ad_classifier.intelligence_crawler.models import (
    IntelArtifactSummary,
    IntelResourceArtifact,
    IntelResourceView,
    IntelSignal,
    IntelSource,
    PollDiagnostic,
    SourceState,
)
from ad_classifier.intelligence_crawler.normalized import build_normalized_resource
from ad_classifier.intelligence_crawler.timeutils import iso, parse_iso


def coerce(value: object) -> object:
    return iso(value) if isinstance(value, datetime) else value


def diagnostics_json(value: object) -> str:
    if not isinstance(value, list):
        return "[]"
    payload = [
        item.model_dump(mode="json") if isinstance(item, PollDiagnostic) else item for item in value
    ]
    return to_json(payload) or "[]"


def source(row: sqlite3.Row) -> IntelSource:
    return IntelSource(
        id=row["id"],
        brand_name=row["brand_name"],
        market=row["market"],
        source_type=row["source_type"],
        tier=row["tier"],
        url=row["url"],
        platform=row["platform"],
        platform_id=row["platform_id"],
        enabled=bool(row["enabled"]),
        poll_interval_hours=float(row["poll_interval_hours"] or 12.0),
        source_activated_at=parse_iso(row["source_activated_at"]),
        allowed_domains=[str(item) for item in (loads_list(row["allowed_domains_json"]) or [])],
        config=loads_dict(row["config_json"]) or {},
        notes=row["notes"],
    )


def state(row: sqlite3.Row) -> SourceState:
    diagnostics = loads_list(row_get(row, "diagnostics_json")) or []
    return SourceState(
        source_id=row["source_id"],
        last_attempt_at=parse_iso(row["last_attempt_at"]),
        last_success_at=parse_iso(row["last_success_at"]),
        next_due_at=parse_iso(row["next_due_at"]),
        last_error=row["last_error"],
        consecutive_errors=int(row["consecutive_errors"] or 0),
        etag=row["etag"],
        last_modified=row["last_modified"],
        watermark=row["watermark"],
        lease_until=parse_iso(row["lease_until"]),
        lease_owner=row["lease_owner"],
        last_outcome=row_get(row, "last_outcome"),
        last_error_category=row_get(row, "last_error_category"),
        last_error_code=row_get(row, "last_error_code"),
        cooldown_until=parse_iso(row_get(row, "cooldown_until")),
        last_diagnostics=[PollDiagnostic.model_validate(item) for item in diagnostics],
    )


def signal(row: sqlite3.Row) -> IntelSignal:
    return IntelSignal(
        id=row["id"],
        brand_name=row["brand_name"],
        campaign_group_id=row["campaign_group_id"],
        signal_type=row["signal_type"],
        status=row["status"],
        confidence=float(row["confidence"] or 0.0),
        title=row["title"],
        summary=row["summary"],
        campaign_name=row["campaign_name"],
        products=[str(item) for item in (loads_list(row["products_json"]) or [])],
        first_seen_at=required_datetime(row["first_seen_at"]),
        source_published_at=parse_iso(row["source_published_at"]),
        last_seen_at=required_datetime(row["last_seen_at"]),
        score_breakdown=loads_dict(row["score_breakdown_json"]) or {},
    )


def resource_view(
    row: sqlite3.Row, media_artifacts: list[IntelResourceArtifact]
) -> IntelResourceView:
    metadata = loads_dict(row["metadata_json"]) or {}
    summary = artifact_summary(metadata, media_asset_count=len(media_artifacts))
    artifacts = [*artifacts_from_metadata(metadata), *media_artifacts]
    published_at = parse_iso(row["published_at"])
    fetched_at = required_datetime(row["fetched_at"])
    variant_count = int_or_none(row_get(row, "variant_count"))
    has_variants = bool(row_get(row, "has_variants") or 0)
    return IntelResourceView(
        id=row["id"],
        brand_name=row["brand_name"],
        source_id=row["source_id"],
        source_type=row["source_type"],
        resource_type=row["resource_type"],
        url=row["url"],
        platform=row_get(row, "platform"),
        platform_id=row["platform_id"],
        title=row["title"],
        description=row["description"],
        published_at=published_at,
        first_seen_at=required_datetime(row["first_seen_at"]),
        last_seen_at=parse_iso(row_get(row, "last_seen_at")),
        fetched_at=fetched_at,
        is_backfill=bool(row["is_backfill"]),
        variant_count=variant_count,
        has_variants=has_variants,
        thumbnail_url=row_get(row, "thumbnail_url"),
        duration_ms=int_or_none(row_get(row, "duration_ms")),
        artifact_summary=summary,
        artifacts=artifacts,
        normalized=build_normalized_resource(
            source_type=str(row["source_type"]),
            brand_name=str(row["brand_name"]),
            resource_type=str(row["resource_type"]),
            url=row["url"],
            platform=row_get(row, "platform"),
            platform_id=row["platform_id"],
            title=row["title"],
            description=row["description"],
            published_at=published_at,
            fetched_at=fetched_at,
            variant_count=variant_count,
            has_variants=has_variants,
            metadata=metadata,
            artifacts=artifacts,
        ),
        metadata=metadata,
    )


def artifact_summary(metadata: dict, *, media_asset_count: int = 0) -> IntelArtifactSummary:
    return IntelArtifactSummary(
        screenshot_count=1 if metadata.get("screenshot_path") else 0,
        image_source_count=len(list_field(metadata, "image_sources")),
        video_source_count=len(list_field(metadata, "video_sources")),
        video_poster_count=len(list_field(metadata, "video_posters")),
        background_image_source_count=len(list_field(metadata, "background_image_sources")),
        link_count=len(list_field(metadata, "links")),
        media_asset_count=media_asset_count,
    )


def merge_artifact_summary(
    left: IntelArtifactSummary, right: IntelArtifactSummary
) -> IntelArtifactSummary:
    return IntelArtifactSummary(
        screenshot_count=left.screenshot_count + right.screenshot_count,
        image_source_count=left.image_source_count + right.image_source_count,
        video_source_count=left.video_source_count + right.video_source_count,
        video_poster_count=left.video_poster_count + right.video_poster_count,
        background_image_source_count=(
            left.background_image_source_count + right.background_image_source_count
        ),
        link_count=left.link_count + right.link_count,
        media_asset_count=left.media_asset_count + right.media_asset_count,
    )


def artifacts_from_metadata(metadata: dict) -> list[IntelResourceArtifact]:
    artifacts: list[IntelResourceArtifact] = []
    screenshot_path = str(metadata.get("screenshot_path") or "").strip()
    if screenshot_path:
        artifacts.append(
            IntelResourceArtifact(
                artifact_type="card_screenshot", label="Card screenshot", path=screenshot_path
            )
        )
    for url in list_field(metadata, "image_sources")[:6]:
        artifacts.append(IntelResourceArtifact(artifact_type="image_url", label="Image", url=url))
    for url in list_field(metadata, "video_sources")[:6]:
        artifacts.append(IntelResourceArtifact(artifact_type="video_url", label="Video", url=url))
    for url in list_field(metadata, "video_posters")[:4]:
        artifacts.append(
            IntelResourceArtifact(artifact_type="video_poster", label="Video poster", url=url)
        )
    for url in list_field(metadata, "background_image_sources")[:4]:
        artifacts.append(
            IntelResourceArtifact(
                artifact_type="background_image", label="Background image", url=url
            )
        )
    for item in raw_list(metadata, "links")[:6]:
        href = str(item.get("href") or "").strip() or None if isinstance(item, dict) else None
        text = str(item.get("text") or "").strip() or None if isinstance(item, dict) else None
        if not isinstance(item, dict):
            href = str(item or "").strip() or None
        if href or text:
            artifacts.append(
                IntelResourceArtifact(
                    artifact_type="link", label=text or "Link", url=href, text=text
                )
            )
    return artifacts


def resource_filters(
    *, brand: str | None, source_id: str | None, include_backfill: bool
) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if brand:
        clauses.append("LOWER(s.brand_name) = LOWER(?)")
        params.append(brand)
    if source_id:
        clauses.append("r.source_id = ?")
        params.append(source_id)
    if not include_backfill:
        clauses.append("r.is_backfill = 0")
    return clauses, params


def source_run_dict(row: sqlite3.Row) -> dict:
    return {
        "run_id": str(row["run_id"]),
        "source_id": str(row["source_id"]),
        "status": str(row["status"]),
        "outcome": row["outcome"],
        "started_at": parse_iso(row["started_at"]),
        "finished_at": parse_iso(row["finished_at"]),
        "complete": bool(row["complete"]),
        "truncated": bool(row["truncated"]),
        "truncation_reason": row["truncation_reason"],
        "new_resources": int(row["new_resources"] or 0),
        "refreshed": int(row["refreshed"] or 0),
        "backfilled": int(row["backfilled"] or 0),
        "filtered": int(row["filtered"] or 0),
        "new_signals": int(row["new_signals"] or 0),
        "failure_category": row["error_category"],
        "error_code": row["error_code"],
        "error": row["error"],
        "diagnostics": loads_list(row["diagnostics_json"]) or [],
        "request_count": int(row["request_count"] or 0),
        "page_count": int(row["page_count"] or 0),
        "provider_item_count": row["provider_item_count"],
        "next_due_at": parse_iso(row["next_due_at"]),
    }


def crawl_run_dict(row: sqlite3.Row) -> dict:
    return {
        "run_id": str(row["id"]),
        "status": str(row["status"]),
        "started_at": parse_iso(row["started_at"]),
        "finished_at": parse_iso(row["finished_at"]),
        "source_count": int(row["source_count"] or 0),
        "resource_count": int(row["resource_count"] or 0),
        "signal_count": int(row["signal_count"] or 0),
        "error": row["error"],
        "summary": loads_dict(row["summary_json"]) or {},
    }


def max_datetime(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def row_get(row: sqlite3.Row, key: str, default: object = None) -> object:
    try:
        return row[key]
    except IndexError:
        return default


def int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


def required_datetime(value: str | None) -> datetime:
    parsed = parse_iso(value)
    assert parsed is not None
    return parsed


def list_field(metadata: dict, key: str) -> list[str]:
    return [str(value).strip() for value in raw_list(metadata, key) if str(value or "").strip()]


def raw_list(metadata: dict, key: str) -> list:
    value = metadata.get(key)
    return value if isinstance(value, list) else []
