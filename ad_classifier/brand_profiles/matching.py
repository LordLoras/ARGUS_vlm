from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import quote

_LEGAL_SUFFIX_RE = re.compile(
    r"\b(incorporated|inc|llc|ltd|limited|corp|corporation|company|co|plc|gmbh|ag|nv)\b",
    flags=re.IGNORECASE,
)


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
        ),
        reverse=True,
    )
    return ranked[0]


def select_wikidata_candidate(
    name: str,
    candidates: list[dict[str, Any]],
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


def _candidate_score(normalized_query: str, title: str, detail: str) -> float:
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
    return score
