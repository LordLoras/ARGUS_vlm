"""Durable Google crawl checkpoints, incremental overlap scans, and preview reuse."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ad_classifier.intelligence_crawler.models import ScanMode, SourceState
from ad_classifier.intelligence_crawler.timeutils import as_utc, parse_iso

STATE_KEY = "google_atc"


@dataclass(frozen=True)
class GoogleScanPlan:
    mode: ScanMode
    initial_after: str | None
    prior_page_count: int
    checkpoint_mode: str | None
    known_index: dict[str, dict[str, Any]]
    stop_after_unchanged_pages: int
    fingerprint: str


def query_fingerprint(advertiser_id: str, *, region: int, page_size: int) -> str:
    raw = f"{advertiser_id}|{region}|{page_size}|newest-first-v1"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def plan_scan(
    state: SourceState,
    *,
    advertiser_id: str,
    region: int,
    page_size: int,
    now: datetime,
    full_reconcile_hours: int,
    checkpoint_ttl_hours: int,
    stop_after_unchanged_pages: int,
) -> GoogleScanPlan:
    fingerprint = query_fingerprint(advertiser_id, region=region, page_size=page_size)
    google = _google_state(state.provider_state)
    checkpoint = google.get("checkpoint")
    if isinstance(checkpoint, dict) and _valid_checkpoint(
        checkpoint, fingerprint, now, checkpoint_ttl_hours
    ):
        return GoogleScanPlan(
            mode="resume",
            initial_after=str(checkpoint["token"]),
            prior_page_count=_as_int(checkpoint.get("page_count")),
            checkpoint_mode=str(checkpoint.get("mode") or "full"),
            known_index=state.runtime_context.get("resource_index", {}),
            stop_after_unchanged_pages=stop_after_unchanged_pages,
            fingerprint=fingerprint,
        )

    known = state.runtime_context.get("resource_index", {})
    last_full = parse_iso(google.get("last_full_success_at"))
    if last_full is None and known:
        last_full = as_utc(state.last_success_at)
    now_utc = as_utc(now)
    assert now_utc is not None
    full_due = last_full is None or now_utc - last_full >= timedelta(hours=full_reconcile_hours)
    return GoogleScanPlan(
        mode="full" if full_due or not known else "incremental",
        initial_after=None,
        prior_page_count=0,
        checkpoint_mode=None,
        known_index=known,
        stop_after_unchanged_pages=0 if full_due or not known else stop_after_unchanged_pages,
        fingerprint=fingerprint,
    )


def with_checkpoint(
    provider_state: dict[str, Any],
    *,
    token: str,
    fingerprint: str,
    mode: str,
    page_count: int,
    now: datetime,
) -> dict[str, Any]:
    output = dict(provider_state)
    google = _google_state(output)
    now_utc = as_utc(now)
    assert now_utc is not None
    google["checkpoint"] = {
        "token": token,
        "fingerprint": fingerprint,
        "mode": mode,
        "page_count": page_count,
        "updated_at": now_utc.isoformat(),
    }
    output[STATE_KEY] = google
    return output


def after_success(
    provider_state: dict[str, Any], *, mode: str, reached_provider_end: bool, now: datetime
) -> dict[str, Any]:
    output = dict(provider_state)
    google = _google_state(output)
    google.pop("checkpoint", None)
    now_utc = as_utc(now)
    assert now_utc is not None
    now_iso = now_utc.isoformat()
    google["last_incremental_success_at"] = now_iso
    if mode == "full" or reached_provider_end:
        google["last_full_success_at"] = now_iso
    output[STATE_KEY] = google
    return output


def clear_checkpoint(provider_state: dict[str, Any]) -> dict[str, Any]:
    output = dict(provider_state)
    google = _google_state(output)
    google.pop("checkpoint", None)
    output[STATE_KEY] = google
    return output


def is_known_unchanged(creative: dict, known_index: dict[str, dict[str, Any]]) -> bool:
    creative_id = str(creative.get("creative_id") or "")
    stored = known_index.get(creative_id)
    if not stored:
        return False
    return creative_signature(creative) == stored_signature(stored)


def creative_signature(creative: dict) -> str:
    return _signature(
        {
            "advertiser_id": creative.get("advertiser_id"),
            "advertiser_name": creative.get("advertiser_name"),
            "format_code": creative.get("format_code"),
            "first_shown": creative.get("first_shown"),
            "last_shown": creative.get("last_shown"),
            "preview_url": creative.get("preview_url"),
            "inline_image_sources": creative.get("image_sources") or [],
            "creative_text": creative.get("text"),
        }
    )


def stored_signature(stored: dict[str, Any]) -> str:
    raw_metadata = stored.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    inline = metadata.get("inline_image_sources")
    if inline is None and metadata.get("has_inline_image"):
        inline = metadata.get("image_sources") or []
    return _signature(
        {
            "advertiser_id": metadata.get("advertiser_id"),
            "advertiser_name": metadata.get("advertiser_name_raw")
            or metadata.get("advertiser_name"),
            "format_code": metadata.get("format_code"),
            "first_shown": metadata.get("first_shown"),
            "last_shown": metadata.get("last_shown"),
            "preview_url": metadata.get("preview_url"),
            "inline_image_sources": inline or [],
            "creative_text": metadata.get("creative_text") or stored.get("description"),
        }
    )


def cached_preview_artifacts(
    creative: dict, known_index: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    stored = known_index.get(str(creative.get("creative_id") or ""))
    metadata = stored.get("metadata") if isinstance(stored, dict) else None
    if not isinstance(metadata, dict) or not metadata.get("preview_enriched"):
        return None
    if str(metadata.get("preview_url") or "") != str(creative.get("preview_url") or ""):
        return None
    return {
        "youtube_video_ids": metadata.get("youtube_video_ids") or [],
        "image_sources": metadata.get("image_sources") or [],
        "video_sources": metadata.get("video_sources") or [],
        "video_posters": metadata.get("video_posters") or [],
        "links": metadata.get("links") or [],
    }


def preview_needs_refresh(creative: dict, known_index: dict[str, dict[str, Any]]) -> bool:
    """Whether an otherwise-known hosted creative still lacks its preview artifacts."""
    preview_url = str(creative.get("preview_url") or "").strip()
    if not preview_url:
        return False
    stored = known_index.get(str(creative.get("creative_id") or ""))
    metadata = stored.get("metadata") if isinstance(stored, dict) else None
    if not isinstance(metadata, dict):
        return False
    return str(metadata.get("preview_url") or "") == preview_url and not metadata.get(
        "preview_enriched"
    )


def checkpoint_summary(provider_state: dict[str, Any]) -> tuple[bool, int | None]:
    checkpoint = _google_state(provider_state).get("checkpoint", {})
    if not isinstance(checkpoint, dict) or not checkpoint.get("token"):
        return False, None
    return True, _as_int(checkpoint.get("page_count"))


def _valid_checkpoint(value: object, fingerprint: str, now: datetime, ttl_hours: int) -> bool:
    if not isinstance(value, dict) or not value.get("token"):
        return False
    if value.get("fingerprint") != fingerprint:
        return False
    updated = parse_iso(value.get("updated_at"))
    now_utc = as_utc(now)
    assert now_utc is not None
    return updated is not None and now_utc - updated <= timedelta(hours=ttl_hours)


def _google_state(provider_state: dict[str, Any]) -> dict[str, Any]:
    value = provider_state.get(STATE_KEY, {})
    return dict(value) if isinstance(value, dict) else {}


def _signature(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_int(value: object) -> int:
    if not isinstance(value, (int, str)):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
