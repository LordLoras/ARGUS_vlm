from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ad_classifier.models.iab import IABContentCategory, IABContentCategoryNode

DEFAULT_IAB_CONTENT_TAXONOMY_PATH = Path(__file__).parent.parent / "Content Taxonomy 3.1.tsv"


@dataclass(frozen=True)
class IABContentTaxonomyEntry:
    unique_id: str
    parent_id: str | None
    name: str
    tier_1: str | None
    tier_2: str | None
    tier_3: str | None
    tier_4: str | None

    @property
    def selected_depth(self) -> int:
        if self.tier_4:
            return 4
        if self.tier_3:
            return 3
        if self.tier_2:
            return 2
        return 1

    @property
    def selected_category(self) -> str:
        if self.tier_4:
            return self.tier_4
        if self.tier_3:
            return self.tier_3
        if self.tier_2:
            return self.tier_2
        return self.tier_1 or self.name

    @property
    def full_path(self) -> str:
        return " > ".join(
            part for part in (self.tier_1, self.tier_2, self.tier_3, self.tier_4) if part
        )


@dataclass(frozen=True)
class IABContentInferenceRule:
    unique_id: str
    terms: tuple[str, ...]
    context_terms: tuple[str, ...] = ()


_BEAUTY_CONTEXT_TERMS = (
    "beauty personal care",
    "beauty",
    "cosmetic",
    "cosmetics",
    "consumer packaged goods",
    "personal care",
    "skin care",
    "skincare",
    "style fashion",
)

_INFERENCE_RULES: tuple[IABContentInferenceRule, ...] = (
    IABContentInferenceRule(
        unique_id="559",
        terms=(
            "skin care",
            "skincare",
            "anti aging",
            "visible aging",
            "fine lines",
            "firmness",
            "radiance",
            "smoothness",
            "moisturizer",
            "moisturiser",
            "serum",
            "facial cream",
            "skin cream",
        ),
        context_terms=_BEAUTY_CONTEXT_TERMS,
    ),
    IABContentInferenceRule(
        unique_id="558",
        terms=("perfume", "fragrance", "cologne", "eau de parfum", "eau de toilette"),
        context_terms=_BEAUTY_CONTEXT_TERMS,
    ),
    IABContentInferenceRule(
        unique_id="554",
        terms=("hair care", "shampoo", "conditioner", "hair serum", "hair color"),
        context_terms=_BEAUTY_CONTEXT_TERMS,
    ),
    IABContentInferenceRule(
        unique_id="555",
        terms=("makeup", "mascara", "lipstick", "foundation", "concealer", "eyeliner", "blush"),
        context_terms=_BEAUTY_CONTEXT_TERMS,
    ),
    IABContentInferenceRule(
        unique_id="556",
        terms=("nail care", "nail polish", "manicure", "pedicure"),
        context_terms=_BEAUTY_CONTEXT_TERMS,
    ),
)

_NEGATED_REASON_RE = re.compile(
    r"\b("
    r"excluded|not\s+the\s+focus|not\s+focus|not\s+directly\s+supported|"
    r"not\s+supported|not\s+primary|secondary\s+only|background\s+only|"
    r"merely\s+accompanies|only\s+accompanies|incidental"
    r")\b",
    re.IGNORECASE,
)

_DIRECT_SUPPORT_RULES: tuple[IABContentInferenceRule, ...] = (
    IABContentInferenceRule(
        unique_id="338",
        terms=(
            "music",
            "song",
            "single",
            "album",
            "artist",
            "band",
            "concert",
            "tour",
            "playlist",
            "radio",
            "dj",
            "singer",
            "rapper",
            "orchestra",
            "music video",
        ),
    ),
    IABContentInferenceRule(
        unique_id="641",
        terms=("animation", "animated", "anime", "manga", "cartoon"),
    ),
)


def load_iab_content_taxonomy(
    path: Path = DEFAULT_IAB_CONTENT_TAXONOMY_PATH,
) -> dict[str, IABContentTaxonomyEntry]:
    return _load_iab_content_taxonomy(str(path.expanduser().resolve()))


@lru_cache(maxsize=4)
def _load_iab_content_taxonomy(path: str) -> dict[str, IABContentTaxonomyEntry]:
    source = Path(path)
    if not source.exists():
        return {}

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle, delimiter="\t")
        header: list[str] | None = None
        for row in rows:
            cleaned = [_clean(value) for value in row]
            if cleaned and cleaned[0] == "Unique ID":
                header = cleaned
                break
        if header is None:
            return {}

        reader = csv.DictReader(handle, delimiter="\t", fieldnames=header)
        entries: dict[str, IABContentTaxonomyEntry] = {}
        for row in reader:
            unique_id = _clean(row.get("Unique ID"))
            if not unique_id:
                continue
            entries[unique_id] = IABContentTaxonomyEntry(
                unique_id=unique_id,
                parent_id=_clean(row.get("Parent")) or None,
                name=_clean(row.get("Name")) or unique_id,
                tier_1=_clean(row.get("Tier 1")) or None,
                tier_2=_clean(row.get("Tier 2")) or None,
                tier_3=_clean(row.get("Tier 3")) or None,
                tier_4=_clean(row.get("Tier 4")) or None,
            )
    return entries


def render_iab_content_taxonomy_for_prompt(
    path: Path = DEFAULT_IAB_CONTENT_TAXONOMY_PATH,
) -> str:
    entries = load_iab_content_taxonomy(path)
    if not entries:
        return "- no IAB content taxonomy file found"
    lines: list[str] = []
    for entry in entries.values():
        parent = entry.parent_id or "root"
        lines.append(
            f"- {entry.unique_id} | parent={parent} | depth={entry.selected_depth} | "
            f"{entry.full_path}"
        )
    return "\n".join(lines)


def iab_content_category_from_id(
    unique_id: str,
    *,
    confidence: str = "medium",
    reason: str = "",
    path: Path = DEFAULT_IAB_CONTENT_TAXONOMY_PATH,
) -> IABContentCategory | None:
    entries = load_iab_content_taxonomy(path)
    entry = entries.get(unique_id)
    if entry is None:
        return None
    return IABContentCategory(
        iab_unique_id=entry.unique_id,
        iab_parent_id=entry.parent_id,
        tier_1=entry.tier_1,
        tier_2=entry.tier_2,
        tier_3=entry.tier_3,
        tier_4=entry.tier_4,
        selected_depth=entry.selected_depth,
        selected_category=entry.selected_category,
        full_path=entry.full_path,
        confidence=confidence,
        reason=reason,
        parent_categories=_parent_categories(entry, entries),
    )


def normalize_iab_content_categories(
    categories: Iterable[IABContentCategory | dict] | None,
    path: Path = DEFAULT_IAB_CONTENT_TAXONOMY_PATH,
) -> list[IABContentCategory]:
    if not categories:
        return []

    entries = load_iab_content_taxonomy(path)
    normalized: list[IABContentCategory] = []
    seen: set[str] = set()
    for candidate in categories:
        if isinstance(candidate, dict):
            try:
                category = IABContentCategory.model_validate(candidate)
            except ValueError:
                continue
        else:
            category = candidate

        if not entries:
            if category.iab_unique_id not in seen:
                normalized.append(category)
                seen.add(category.iab_unique_id)
            continue

        entry = entries.get(category.iab_unique_id) or _find_entry(category, entries)
        if entry is None or entry.unique_id in seen:
            continue

        normalized.append(
            IABContentCategory(
                iab_unique_id=entry.unique_id,
                iab_parent_id=entry.parent_id,
                tier_1=entry.tier_1,
                tier_2=entry.tier_2,
                tier_3=entry.tier_3,
                tier_4=entry.tier_4,
                selected_depth=entry.selected_depth,
                selected_category=entry.selected_category,
                full_path=entry.full_path,
                confidence=category.confidence,
                reason=category.reason,
                parent_categories=_parent_categories(entry, entries),
            )
        )
        seen.add(entry.unique_id)
    return normalized


def infer_iab_content_categories(
    *,
    existing: Iterable[IABContentCategory | dict] | None = None,
    primary_category: str | None = None,
    subcategory: str | None = None,
    products: Iterable[str] | None = None,
    product_iab_path: str | None = None,
    evidence_texts: Iterable[str] | None = None,
    path: Path = DEFAULT_IAB_CONTENT_TAXONOMY_PATH,
) -> list[IABContentCategory]:
    normalized = normalize_iab_content_categories(existing, path)
    blob = _inference_blob(
        [
            primary_category,
            subcategory,
            product_iab_path,
            *(products or []),
            *(evidence_texts or []),
        ]
    )
    normalized = _filter_supported_existing(normalized, blob)
    seen = {category.iab_unique_id for category in normalized}
    if not blob:
        return normalized

    for rule in _INFERENCE_RULES:
        if rule.unique_id in seen:
            continue
        if rule.context_terms and not _any_term_matches(blob, rule.context_terms):
            continue
        matched_terms = _matched_terms(blob, rule.terms)
        if not matched_terms:
            continue
        category = iab_content_category_from_id(
            rule.unique_id,
            confidence="medium",
            reason=(
                "Deterministic fallback matched extracted ad text: " + ", ".join(matched_terms[:3])
            ),
            path=path,
        )
        if category is not None:
            normalized.append(category)
            seen.add(category.iab_unique_id)

    return normalized


def _filter_supported_existing(
    categories: list[IABContentCategory],
    evidence_blob: str,
) -> list[IABContentCategory]:
    filtered: list[IABContentCategory] = []
    for category in categories:
        if _NEGATED_REASON_RE.search(category.reason or ""):
            continue
        support_rule = _support_rule_for(category)
        if support_rule is not None and evidence_blob:
            matched_terms = _matched_terms(evidence_blob, support_rule.terms)
            if not matched_terms:
                continue
        filtered.append(category)
    return filtered


def _support_rule_for(category: IABContentCategory) -> IABContentInferenceRule | None:
    category_ids = {category.iab_unique_id, *(node.iab_unique_id for node in category.parent_categories)}
    path = _inference_blob([category.full_path, category.selected_category])
    for rule in _DIRECT_SUPPORT_RULES:
        if rule.unique_id in category_ids:
            return rule
    if "animation anime" in path:
        return next(rule for rule in _DIRECT_SUPPORT_RULES if rule.unique_id == "641")
    if "music" in path and "musical instruments" not in path:
        return next(rule for rule in _DIRECT_SUPPORT_RULES if rule.unique_id == "338")
    return None


def _find_entry(
    category: IABContentCategory,
    entries: dict[str, IABContentTaxonomyEntry],
) -> IABContentTaxonomyEntry | None:
    wanted_path = _key(category.full_path)
    wanted_selected = _key(category.selected_category)
    for entry in entries.values():
        if wanted_path and _key(entry.full_path) == wanted_path:
            return entry
        if wanted_selected and _key(entry.selected_category) == wanted_selected:
            return entry
    return None


def _parent_categories(
    entry: IABContentTaxonomyEntry,
    entries: dict[str, IABContentTaxonomyEntry],
) -> list[IABContentCategoryNode]:
    chain: list[IABContentCategoryNode] = []
    parent_id = entry.parent_id
    seen: set[str] = {entry.unique_id}
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = entries.get(parent_id)
        if parent is None:
            break
        chain.append(
            IABContentCategoryNode(
                iab_unique_id=parent.unique_id,
                name=parent.selected_category,
                depth=parent.selected_depth,
                full_path=parent.full_path,
            )
        )
        parent_id = parent.parent_id
    return list(reversed(chain))


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _key(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _inference_blob(values: Iterable[str | None]) -> str:
    text = " ".join(value for value in values if value)
    normalized = re.sub(r"[_\-/]+", " ", text.casefold())
    normalized = re.sub(r"[^a-z0-9& ]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _any_term_matches(blob: str, terms: Iterable[str]) -> bool:
    return bool(_matched_terms(blob, terms))


def _matched_terms(blob: str, terms: Iterable[str]) -> list[str]:
    matched: list[str] = []
    for term in terms:
        normalized = _inference_blob([term])
        if normalized and f" {normalized} " in f" {blob} ":
            matched.append(term)
    return matched
