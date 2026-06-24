"""Stable, content-derived identifiers for intelligence-crawler rows.

Reuses the entity-graph digest helper so id generation is consistent across the repo.
Every id is deterministic from its inputs, so re-polling the same external item yields
the same row id (the basis for idempotent change detection).
"""

from __future__ import annotations

import uuid

from ad_classifier.entity_graph.utils import digest


def resource_id(source_id: str, external_id: str) -> str:
    return "res_" + digest(source_id, external_id)[:20]


def signal_id(source_id: str, external_id: str, signal_type: str) -> str:
    return "sig_" + digest(source_id, external_id, signal_type)[:20]


def campaign_group_id(brand_name: str, group_key: str) -> str:
    return "grp_" + digest(brand_name, group_key)[:20]


def evidence_id(signal_id_: str, resource_id_: str | None) -> str:
    return "ev_" + digest(signal_id_, resource_id_ or "")[:20]


def match_id(signal_id_: str, target_type: str, target_id: str) -> str:
    return "mat_" + digest(signal_id_, target_type, target_id)[:20]


def new_run_id() -> str:
    return f"intel_run_{uuid.uuid4().hex[:12]}"
