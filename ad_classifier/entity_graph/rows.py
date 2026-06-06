from __future__ import annotations

import json
import sqlite3

from ad_classifier.entity_graph.models import (
    AdChangeSuggestion,
    CrawlerResult,
    CrawlerRunRecord,
    EntityAlias,
    EntityEdge,
    EntityNode,
    EntityObservation,
    EntitySource,
    TaxonomyMapping,
)


def to_json(value: dict | list | None) -> str | None:
    return json.dumps(value, sort_keys=True) if value is not None else None


def loads_dict(value: str | None) -> dict | None:
    if not value:
        return None
    parsed = json.loads(value)
    return parsed if isinstance(parsed, dict) else None


def loads_list(value: str | None) -> list | None:
    if not value:
        return None
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else None


def crawler_run(row: sqlite3.Row) -> CrawlerRunRecord:
    result_payload = loads_dict(row["result_json"])
    return CrawlerRunRecord(
        id=row["id"],
        status=row["status"],
        rerun_mode=row["rerun_mode"],
        limit=int(row["limit_value"] or 100),
        ad_ids=[str(item) for item in (loads_list(row["ad_ids_json"]) or [])],
        target_urls=loads_dict(row["target_urls_json"]) or {},
        result=CrawlerResult.model_validate(result_payload) if result_payload else None,
        error=row["error"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def source(row: sqlite3.Row) -> EntitySource:
    return EntitySource(
        id=row["id"],
        source_type=row["source_type"],
        label=row["label"],
        url=row["url"],
        ad_id=row["ad_id"],
        payload=loads_dict(row["payload_json"]),
        created_at=row["created_at"],
    )


def node(row: sqlite3.Row) -> EntityNode:
    return EntityNode(
        id=row["id"],
        type=row["type"],
        canonical_name=row["canonical_name"],
        normalized_name=row["normalized_name"],
        description=row["description"],
        status=row["status"],
        confidence=float(row["confidence"] or 0.0),
        generated_from=loads_dict(row["generated_from_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def joined_node(row: sqlite3.Row) -> EntityNode:
    return EntityNode(
        id=row["n_id"],
        type=row["n_type"],
        canonical_name=row["n_name"],
        normalized_name=row["n_norm"],
        description=row["n_desc"],
        status=row["n_status"],
        confidence=float(row["n_confidence"] or 0.0),
        generated_from=loads_dict(row["n_generated"]),
        created_at=row["n_created_at"],
        updated_at=row["n_updated_at"],
    )


def alias(row: sqlite3.Row) -> EntityAlias:
    return EntityAlias(
        id=row["id"],
        node_id=row["node_id"],
        alias=row["alias"],
        normalized_alias=row["normalized_alias"],
        source_id=row["source_id"],
        confidence=float(row["confidence"] or 0.0),
        status=row["status"],
        created_at=row["created_at"],
    )


def edge(row: sqlite3.Row) -> EntityEdge:
    return EntityEdge(
        id=row["id"],
        source_node_id=row["source_node_id"],
        target_node_id=row["target_node_id"],
        relation=row["relation"],
        confidence=float(row["confidence"] or 0.0),
        status=row["status"],
        source_id=row["source_id"],
        evidence=loads_dict(row["evidence_json"]),
        created_at=row["created_at"],
    )


def observation(row: sqlite3.Row) -> EntityObservation:
    return EntityObservation(
        id=row["id"],
        node_id=row["node_id"],
        ad_id=row["ad_id"],
        field=row["field"],
        evidence_text=row["evidence_text"],
        source=row["source"],
        time_ms=row["time_ms"],
        frame_index=row["frame_index"],
        confidence=float(row["confidence"] or 0.0),
        source_id=row["source_id"],
        created_at=row["created_at"],
    )


def mapping(row: sqlite3.Row) -> TaxonomyMapping:
    return TaxonomyMapping(
        id=row["id"],
        entity_id=row["entity_id"],
        taxonomy_type=row["taxonomy_type"],
        taxonomy_id=row["taxonomy_id"],
        taxonomy_name=row["taxonomy_name"],
        relation=row["relation"],
        confidence=float(row["confidence"] or 0.0),
        status=row["status"],
        source_id=row["source_id"],
        evidence_text=row["evidence_text"],
        created_at=row["created_at"],
    )


def suggestion(row: sqlite3.Row) -> AdChangeSuggestion:
    return AdChangeSuggestion(
        id=row["id"],
        ad_id=row["ad_id"],
        source_id=row["source_id"],
        field_path=row["field_path"],
        current_value=row["current_value"],
        suggested_value=row["suggested_value"],
        confidence=float(row["confidence"] or 0.0),
        reason=row["reason"],
        evidence_text=row["evidence_text"],
        status=row["status"],
        apply_safety=row["apply_safety"],
        payload=loads_dict(row["payload_json"]),
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
        applied_at=row["applied_at"],
    )
