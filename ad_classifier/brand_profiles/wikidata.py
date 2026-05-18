from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from ad_classifier.brand_profiles.matching import unique

ENTITY_PROPS = {
    "P749": "parent_companies",
    "P127": "owners",
    "P452": "industries",
    "P159": "headquarters",
    "P17": "countries",
    "P112": "founded_by",
    "P355": "subsidiaries",
}

METRIC_PROPS = {
    "P1128": "employees",
    "P2139": "revenue",
    "P2295": "net income",
    "P2403": "total assets",
    "P2137": "total equity",
    "P3362": "operating income",
}


def collect_label_qids(entity: dict[str, Any]) -> list[str]:
    qids: list[str] = []
    claims = entity.get("claims", {})
    if not isinstance(claims, dict):
        return qids
    for prop in [*ENTITY_PROPS.keys(), *METRIC_PROPS.keys()]:
        for claim in claims.get(prop, []):
            qid = _claim_entity_id(claim)
            if qid:
                qids.append(qid)
            quantity = _claim_quantity(claim)
            unit_qid = _unit_qid(quantity.get("unit")) if quantity else None
            if unit_qid:
                qids.append(unit_qid)
    return unique(qids)


def entity_self_label_map(entity: dict[str, Any]) -> dict[str, str]:
    qid = entity.get("id")
    label = entity_label(entity)
    return {str(qid): label} if qid and label else {}


def entity_label(entity: dict[str, Any]) -> str | None:
    value = entity.get("labels", {}).get("en", {}).get("value")
    return str(value) if value else None


def entity_description(entity: dict[str, Any]) -> str | None:
    value = entity.get("descriptions", {}).get("en", {}).get("value")
    return str(value) if value else None


def entity_ids(entity: dict[str, Any], prop: str, *, limit: int = 12) -> list[str]:
    claims = entity.get("claims", {})
    if not isinstance(claims, dict):
        return []
    qids = [_claim_entity_id(claim) for claim in claims.get(prop, [])]
    return unique([qid for qid in qids if qid])[:limit]


def entity_labels(
    entity: dict[str, Any],
    prop: str,
    labels: dict[str, str],
    *,
    limit: int = 12,
) -> list[str]:
    return labels_for_qids(entity_ids(entity, prop, limit=limit), labels)


def labels_for_qids(qids: list[str], labels: dict[str, str]) -> list[str]:
    return unique([labels.get(qid, qid) for qid in qids])


def claim_url(entity: dict[str, Any], prop: str) -> str | None:
    claims = entity.get("claims", {})
    if not isinstance(claims, dict):
        return None
    for claim in claims.get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, str) and value:
            return value
    return None


def claim_time(entity: dict[str, Any], prop: str) -> str | None:
    claims = entity.get("claims", {})
    if not isinstance(claims, dict):
        return None
    for claim in claims.get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("time"):
            return _format_wikidata_time(str(value["time"]))
    return None


def metrics(entity: dict[str, Any], labels: dict[str, str]) -> dict[str, str | list[str]]:
    claims = entity.get("claims", {})
    if not isinstance(claims, dict):
        return {}
    extracted: dict[str, str | list[str]] = {}
    for prop, label in METRIC_PROPS.items():
        values: list[str] = []
        for claim in claims.get(prop, [])[:3]:
            quantity = _claim_quantity(claim)
            if not quantity:
                continue
            formatted = _format_quantity(quantity, labels)
            point_in_time = _claim_qualifier_time(claim, "P585")
            if point_in_time:
                formatted = f"{formatted} ({point_in_time})"
            values.append(formatted)
        if len(values) == 1:
            extracted[label] = values[0]
        elif values:
            extracted[label] = values
    return extracted


def _claim_entity_id(claim: dict[str, Any]) -> str | None:
    value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
    if isinstance(value, dict) and value.get("id"):
        return str(value["id"])
    return None


def _claim_quantity(claim: dict[str, Any]) -> dict[str, Any]:
    value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
    return value if isinstance(value, dict) and "amount" in value else {}


def _claim_qualifier_time(claim: dict[str, Any], prop: str) -> str | None:
    qualifiers = claim.get("qualifiers", {})
    if not isinstance(qualifiers, dict):
        return None
    for qualifier in qualifiers.get(prop, []):
        value = qualifier.get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("time"):
            return _format_metric_time(str(value["time"]))
    return None


def _format_quantity(quantity: dict[str, Any], labels: dict[str, str]) -> str:
    amount = str(quantity.get("amount") or "")
    unit = quantity.get("unit")
    try:
        number = Decimal(amount.lstrip("+"))
        text = f"{int(number):,}" if number == number.to_integral() else f"{number.normalize():,}"
    except (InvalidOperation, ValueError):
        text = amount.lstrip("+") or "unknown"
    unit_qid = _unit_qid(str(unit)) if unit else None
    if unit_qid and labels.get(unit_qid):
        text = f"{text} {labels[unit_qid]}"
    return text


def _unit_qid(unit: str | None) -> str | None:
    if not unit or unit == "1":
        return None
    tail = unit.rstrip("/").split("/")[-1]
    return tail if tail.startswith("Q") else None


def _format_wikidata_time(raw: str) -> str:
    value = raw.lstrip("+")
    date = value.split("T", 1)[0]
    parts = date.split("-")
    if len(parts) >= 2 and parts[1] == "00":
        return parts[0]
    if len(parts) >= 3 and parts[2] == "00":
        return "-".join(parts[:2])
    return date


def _format_metric_time(raw: str) -> str:
    return raw.lstrip("+")[:4] or _format_wikidata_time(raw)
