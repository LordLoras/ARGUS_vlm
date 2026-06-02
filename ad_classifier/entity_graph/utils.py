from __future__ import annotations

import hashlib
import re

STATUS_RANK: dict[str, int] = {
    "candidate": 0,
    "confirmed_unreviewed": 1,
    "confirmed_reviewed": 2,
    "rejected": 3,
}


def normalize_name(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def merge_status(existing: str, incoming: str) -> str:
    if existing == "rejected":
        return existing
    return incoming if STATUS_RANK[incoming] > STATUS_RANK[existing] else existing


def source_id(source_type: str, label: str, url: str | None, ad_id: str | None) -> str:
    return "src_" + digest(source_type, label, url or "", ad_id or "")[:20]


def node_id(entity_type: str, normalized: str) -> str:
    return f"n_{entity_type}_{digest(entity_type, normalized)[:16]}"


def edge_id(source_node_id: str, relation: str, target_node_id: str, source_id_: str | None) -> str:
    return "e_" + digest(source_node_id, relation, target_node_id, source_id_ or "")[:20]


def observation_id(node_id_: str, ad_id: str, field: str, text: str, source: str) -> str:
    return "obs_" + digest(node_id_, ad_id, field, text, source)[:20]


def mapping_id(entity_id: str, taxonomy_type: str, taxonomy_id: str, source_id_: str | None) -> str:
    return "map_" + digest(entity_id, taxonomy_type, taxonomy_id, source_id_ or "")[:20]


def digest(*parts: str) -> str:
    h = hashlib.sha1()
    h.update("\x1f".join(parts).encode("utf-8"))
    return h.hexdigest()
