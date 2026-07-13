"""Stable consumer contract helpers for pagination and resource change detection."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from typing import Any

from ad_classifier.entity_graph.rows import to_json
from ad_classifier.intelligence_crawler.models import IntelResource
from ad_classifier.intelligence_crawler.timeutils import iso

INTELLIGENCE_SCHEMA_VERSION = "1.0"


def encode_cursor(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> dict[str, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid cursor") from exc
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in decoded.items()
    ):
        raise ValueError("invalid cursor")
    return decoded


def resource_snapshot(resource: IntelResource) -> dict[str, Any]:
    """Return semantic fields only; collection timestamps never create false changes."""

    return {
        "id": resource.id,
        "source_id": resource.source_id,
        "resource_type": resource.resource_type,
        "url": resource.url,
        "canonical_url": resource.canonical_url,
        "platform": resource.platform,
        "platform_id": resource.platform_id,
        "content_hash": resource.content_hash,
        "title": resource.title,
        "description": resource.description,
        "published_at": iso(resource.published_at),
        "variant_count": resource.variant_count,
        "has_variants": resource.has_variants,
        "thumbnail_url": resource.thumbnail_url,
        "duration_ms": resource.duration_ms,
        "metadata": resource.metadata,
    }


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(to_json(snapshot).encode("utf-8")).hexdigest()


def resource_cursor_values(resource) -> dict[str, str]:
    sort_at: datetime = resource.published_at or resource.first_seen_at
    return {
        "sort_at": iso(sort_at) or "",
        "first_seen_at": iso(resource.first_seen_at) or "",
        "id": resource.id,
    }
