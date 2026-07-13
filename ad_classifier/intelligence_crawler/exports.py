"""Versioned latest-resource exports and atomic service snapshots."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ad_classifier.intelligence_crawler.contract import INTELLIGENCE_SCHEMA_VERSION
from ad_classifier.intelligence_crawler.timeutils import iso, utcnow

if TYPE_CHECKING:
    from ad_classifier.intelligence_crawler.manager import IntelManager

ExportFormat = Literal["json", "jsonl"]


def iter_latest_resources(
    manager: IntelManager,
    *,
    brand: str | None = None,
    source_id: str | None = None,
    include_backfill: bool = True,
    page_size: int = 250,
) -> Iterator[dict[str, Any]]:
    cursor: str | None = None
    while True:
        items, next_cursor = manager.list_resources_page(
            brand=brand,
            source_id=source_id,
            include_backfill=include_backfill,
            limit=page_size,
            cursor=cursor,
        )
        for item in items:
            yield item.model_dump(mode="json")
        if not next_cursor:
            return
        cursor = next_cursor


def iter_resource_export(
    manager: IntelManager,
    *,
    export_format: ExportFormat,
    brand: str | None = None,
    source_id: str | None = None,
    include_backfill: bool = True,
) -> Iterator[str]:
    resources = iter_latest_resources(
        manager,
        brand=brand,
        source_id=source_id,
        include_backfill=include_backfill,
    )
    if export_format == "jsonl":
        for resource in resources:
            yield _json(resource) + "\n"
        return
    yield _json(
        {
            "schema_version": INTELLIGENCE_SCHEMA_VERSION,
            "generated_at": iso(utcnow()),
            "items": [],
        }
    )[:-2]
    first = True
    for resource in resources:
        yield ("" if first else ",") + _json(resource)
        first = False
    yield "]}"


def write_resource_export(
    manager: IntelManager,
    output_path: Path,
    *,
    export_format: ExportFormat = "json",
    brand: str | None = None,
    source_id: str | None = None,
    include_backfill: bool = True,
) -> Path:
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.writelines(
            iter_resource_export(
                manager,
                export_format=export_format,
                brand=brand,
                source_id=source_id,
                include_backfill=include_backfill,
            )
        )
    temporary.replace(output_path)
    return output_path


def write_latest_snapshots(manager: IntelManager, directory: Path) -> list[Path]:
    directory = directory.expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    generated_at = iso(utcnow())
    resources_path = write_resource_export(manager, directory / "latest_resources.json")
    statuses = [item.model_dump(mode="json") for item in manager.list_source_statuses()]
    statuses_path = _write_json_atomic(
        directory / "source_statuses.json",
        {
            "schema_version": INTELLIGENCE_SCHEMA_VERSION,
            "generated_at": generated_at,
            "items": statuses,
        },
    )
    health_path = _write_json_atomic(directory / "health.json", manager.health())
    return [resources_path, statuses_path, health_path]


def _write_json_atomic(path: Path, payload: Any) -> Path:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(_json(payload) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        default=lambda item: iso(item) if isinstance(item, datetime) else str(item),
    )
