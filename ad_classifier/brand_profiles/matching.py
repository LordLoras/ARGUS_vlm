from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

_LEGAL_SUFFIX_RE = re.compile(
    r"\b(incorporated|inc|llc|ltd|limited|corp|corporation|company|co|plc|gmbh|ag|nv)\b",
    flags=re.IGNORECASE,
)

_DISAMBIG_PHRASES = re.compile(
    r"may refer to|commonly refers to|can refer to|might refer to|could refer to",
    flags=re.IGNORECASE,
)

# Category id → terms that indicate the Wikipedia article is about a brand in this space.
_CATEGORY_TERMS: dict[str, list[str]] = {
    "automotive": ["automaker", "vehicle", "truck", "car", "motor", "pickup", "suv", "automobile", "marque"],
    "financial_services": ["bank", "financial", "insurance", "credit", "mortgage", "investment"],
    "technology": ["technology", "software", "hardware", "tech", "electronics", "computer"],
    "healthcare_pharma": ["pharmaceutical", "health", "medical", "biotech", "drug"],
    "food_beverage": ["food", "beverage", "restaurant", "drink", "snack", "brewery"],
    "retail": ["retail", "store", "shop", "retailer", "chain"],
    "telecommunications": ["telecom", "wireless", "carrier", "network", "broadband"],
    "travel_hospitality": ["airline", "hotel", "resort", "travel", "hospitality"],
    "entertainment": ["entertainment", "media", "studio", "streaming", "broadcast"],
    "energy": ["energy", "oil", "gas", "petroleum", "utility", "power"],
    "real_estate": ["real estate", "property", "housing", "development", "construction"],
    "education": ["education", "university", "school", "learning", "academy"],
}


@dataclass
class SearchContext:
    category: str | None = None
    products: list[str] = field(default_factory=list)
    parent_company: str | None = None


def normalize_profile_name(name: str) -> str:
    text = re.sub(r"[\u2122\u00ae\u00a9]", "", name)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u2122\u00ae\u00a9]", "", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    text = _LEGAL_SUFFIX_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def selected_title(selected: dict[str, Any] | None) -> str | None:
    return str(selected["title"]) if selected and selected.get("title") else None


def selected_page_id(selected: dict[str, Any] | None) -> int | None:
    return int_or_none(selected.get("pageid")) if selected else None


def select_wikipedia_candidate(
    name: str,
    candidates: list[dict[str, Any]],
    context: SearchContext | None = None,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    normalized = normalize_profile_name(name)
    ranked = sorted(
        candidates,
        key=lambda candidate: _candidate_score(
            normalized,
            str(candidate.get("title") or ""),
            str(candidate.get("snippet") or ""),
            context=context,
        ),
        reverse=True,
    )
    return ranked[0]


def select_wikidata_candidate(
    name: str,
    candidates: list[dict[str, Any]],
    context: SearchContext | None = None,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    normalized = normalize_profile_name(name)
    ranked = sorted(
        candidates,
        key=lambda candidate: _candidate_score(
            normalized,
            str(candidate.get("label") or ""),
            str(candidate.get("description") or ""),
            context=context,
        ),
        reverse=True,
    )
    return ranked[0]


def candidate_digest(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "title": candidate.get("title"),
            "pageid": candidate.get("pageid"),
            "snippet": strip_html(str(candidate.get("snippet") or ""))[:240] or None,
        }
        for candidate in candidates
    ]


def first_unseen(qids: list[str], seen: set[str]) -> str | None:
    return next((qid for qid in qids if qid not in seen), None)


def unique(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    unique_values: list[Any] = []
    for value in values:
        if value in (None, "") or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def wiki_url(title: str | None) -> str | None:
    return f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}" if title else None


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _candidate_score(
    normalized_query: str,
    title: str,
    detail: str,
    *,
    context: SearchContext | None = None,
) -> float:
    title_norm = normalize_profile_name(title)
    detail_norm = normalize_profile_name(strip_html(detail))
    score = 0.0
    if title_norm == normalized_query:
        score += 8.0
    if title_norm.startswith(normalized_query) or normalized_query.startswith(title_norm):
        score += 3.0
    query_tokens = set(normalized_query.split())
    title_tokens = set(title_norm.split())
    if query_tokens:
        score += 2.0 * (len(query_tokens & title_tokens) / len(query_tokens))
    for term in ("brand", "company", "manufacturer", "automaker", "corporation", "business"):
        if term in detail_norm:
            score += 0.8
    for term in ("song", "album", "film", "episode", "game", "character"):
        if term in detail_norm:
            score -= 1.0

    # Penalize disambiguation-style snippets.
    if _DISAMBIG_PHRASES.search(detail):
        score -= 3.0

    # Context-aware boosting.
    if context is not None:
        if context.category and context.category in _CATEGORY_TERMS:
            for term in _CATEGORY_TERMS[context.category]:
                if term in detail_norm or term in title_norm:
                    score += 1.5
                    break
        if context.parent_company:
            parent_norm = normalize_profile_name(context.parent_company)
            if parent_norm in detail_norm or parent_norm in title_norm:
                score += 2.0
        for product in context.products[:3]:
            product_norm = normalize_profile_name(product)
            product_tokens = set(product_norm.split())
            if product_tokens & (set(detail_norm.split()) | set(title_norm.split())):
                score += 1.0
                break

    return score


def is_disambiguation(candidates: list[dict[str, Any]]) -> bool:
    """Heuristic: top candidates look like a disambiguation page."""
    if not candidates:
        return False
    top_snippet = str(candidates[0].get("snippet") or candidates[0].get("description") or "")
    if _DISAMBIG_PHRASES.search(top_snippet):
        return True
    # Many short, unrelated snippets suggest disambiguation.
    if len(candidates) >= 3:
        titles = [normalize_profile_name(str(c.get("title") or c.get("label") or "")) for c in candidates[:4]]
        shared = set(titles[0].split()) if titles[0] else set()
        for t in titles[1:]:
            shared &= set(t.split())
        if not shared:
            return True
    return False


def enriched_queries(name: str, context: SearchContext) -> list[str]:
    """Build fallback queries enriched with ad context."""
    queries: list[str] = []
    if context.parent_company:
        queries.append(f"{name} {context.parent_company}")
    if context.category and context.category in _CATEGORY_TERMS:
        # Pick the most specific term for the category.
        queries.append(f"{name} {context.category}")
        queries.append(f"{name} {_CATEGORY_TERMS[context.category][0]}")
    if context.products:
        # Use the first product's type word as a qualifier.
        first_product = context.products[0]
        tokens = first_product.split()
        if len(tokens) > 1:
            queries.append(f"{name} {tokens[-1]}")
    return queries
