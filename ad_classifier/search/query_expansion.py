from __future__ import annotations

import re
from collections.abc import Iterable

DEFAULT_AD_SEARCH_COLUMNS = (
    "id",
    "brand_name",
    "advertiser_name",
    "products_text",
    "primary_category",
    "website_domain",
    "phone_number",
    "landing_page_domain",
)

_ALIASES: dict[str, tuple[str, ...]] = {
    "hvac": (
        "hvac",
        "heating",
        "cooling",
        "air conditioning",
        "air conditioner",
        "furnace",
        "ventilation",
    ),
    "service": (
        "service",
        "services",
        "repair",
        "installation",
        "maintenance",
        "contractor",
        "estimate",
        "appointment",
        "heating",
        "cooling",
        "air conditioning",
        "plumbing",
        "roofing",
        "electrical",
        "pest control",
        "lawn care",
        "cleaning",
    ),
    "services": (
        "service",
        "services",
        "repair",
        "installation",
        "maintenance",
        "contractor",
        "estimate",
        "appointment",
        "heating",
        "cooling",
        "air conditioning",
        "plumbing",
        "roofing",
        "electrical",
        "pest control",
        "lawn care",
        "cleaning",
    ),
}


def expand_query_terms(query: str | None) -> list[str]:
    """Expand common business shorthand into terms present in stored ad text."""
    normalized = " ".join((query or "").strip().split())
    if not normalized:
        return []

    terms = [normalized]
    lowered = normalized.lower()
    tokens = set(re.findall(r"[a-z0-9]+", lowered))

    for trigger, expansions in _ALIASES.items():
        if trigger in tokens or trigger in lowered:
            terms.extend(expansions)

    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        key = term.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(term)
    return deduped


def has_alias_expansion(query: str | None) -> bool:
    terms = expand_query_terms(query)
    return len(terms) > 1


def build_loose_like_clause(
    query: str | None,
    *,
    columns: Iterable[str] = DEFAULT_AD_SEARCH_COLUMNS,
) -> tuple[str | None, list[str]]:
    terms = expand_query_terms(query)
    cols = tuple(columns)
    if not terms or not cols:
        return None, []

    term_clauses: list[str] = []
    params: list[str] = []
    for term in terms:
        term_clauses.append("(" + " OR ".join(f"{column} LIKE ?" for column in cols) + ")")
        params.extend(f"%{term}%" for _ in cols)

    return "(" + " OR ".join(term_clauses) + ")", params
