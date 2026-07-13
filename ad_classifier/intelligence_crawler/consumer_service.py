"""Cursor-based latest-resource and semantic-change consumer reads."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from ad_classifier.intelligence_crawler.contract import (
    decode_cursor,
    encode_cursor,
    resource_cursor_values,
)
from ad_classifier.intelligence_crawler.timeutils import iso

if TYPE_CHECKING:
    from ad_classifier.intelligence_crawler.models import IntelResourceView
    from ad_classifier.intelligence_crawler.repository import IntelRepository


def list_resources_page(
    repo: IntelRepository,
    *,
    brand: str | None = None,
    source_id: str | None = None,
    include_backfill: bool = True,
    limit: int = 50,
    offset: int = 0,
    cursor: str | None = None,
) -> tuple[list[IntelResourceView], str | None]:
    after = None
    if cursor:
        decoded = decode_cursor(cursor)
        try:
            after = (decoded["sort_at"], decoded["first_seen_at"], decoded["id"])
        except KeyError as exc:
            raise ValueError("invalid resource cursor") from exc
    with repo.connect(readonly=True) as conn:
        resources = repo.list_resources(
            conn,
            brand=brand,
            source_id=source_id,
            include_backfill=include_backfill,
            limit=limit + 1,
            offset=offset,
            after=after,
        )
    has_more = len(resources) > limit
    items = resources[:limit]
    next_cursor = encode_cursor(resource_cursor_values(items[-1])) if has_more and items else None
    return items, next_cursor


def list_resource_changes(
    repo: IntelRepository,
    *,
    since: datetime | None = None,
    cursor: str | None = None,
    brand: str | None = None,
    source_id: str | None = None,
    limit: int = 50,
) -> tuple[list[dict], str | None]:
    after = None
    if cursor:
        decoded = decode_cursor(cursor)
        try:
            after = (decoded["changed_at"], decoded["id"])
        except KeyError as exc:
            raise ValueError("invalid change cursor") from exc
    with repo.connect(readonly=True) as conn:
        changes = repo.list_resource_changes(
            conn,
            since=since,
            after=after,
            brand=brand,
            source_id=source_id,
            limit=limit + 1,
        )
        has_more = len(changes) > limit
        changes = changes[:limit]
        items = []
        for change in changes:
            resource = repo.get_resource(conn, change["resource_id"])
            if resource is not None:
                items.append({**change, "resource": resource.model_dump(mode="json")})
    next_cursor = None
    if has_more and changes:
        last = changes[-1]
        next_cursor = encode_cursor(
            {"changed_at": iso(last["changed_at"]) or "", "id": last["change_id"]}
        )
    return items, next_cursor
