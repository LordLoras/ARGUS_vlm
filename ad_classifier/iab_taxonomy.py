from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ad_classifier.models.iab import IABAlternativeCategory, IABCategory, IABCategoryNode

DEFAULT_IAB_TAXONOMY_PATH = Path(__file__).parent.parent / "Ad Product Taxonomy 2.0.tsv"


@dataclass(frozen=True)
class IABTaxonomyEntry:
    unique_id: str
    parent_id: str | None
    name: str
    tier_1: str | None
    tier_2: str | None
    tier_3: str | None

    @property
    def selected_depth(self) -> int:
        if self.tier_3:
            return 3
        if self.tier_2:
            return 2
        return 1

    @property
    def selected_category(self) -> str:
        if self.tier_3:
            return self.tier_3
        if self.tier_2:
            return self.tier_2
        return self.tier_1 or self.name

    @property
    def full_path(self) -> str:
        return " > ".join(part for part in (self.tier_1, self.tier_2, self.tier_3) if part)


def load_iab_taxonomy(path: Path = DEFAULT_IAB_TAXONOMY_PATH) -> dict[str, IABTaxonomyEntry]:
    return _load_iab_taxonomy(str(path.expanduser().resolve()))


@lru_cache(maxsize=4)
def _load_iab_taxonomy(path: str) -> dict[str, IABTaxonomyEntry]:
    source = Path(path)
    if not source.exists():
        return {}

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        entries: dict[str, IABTaxonomyEntry] = {}
        for row in reader:
            unique_id = _clean(row.get("Unique ID"))
            if not unique_id:
                continue
            entries[unique_id] = IABTaxonomyEntry(
                unique_id=unique_id,
                parent_id=_clean(row.get("Parent ID")) or None,
                name=_clean(row.get("Name")) or unique_id,
                tier_1=_clean(row.get("Tier 1")) or None,
                tier_2=_clean(row.get("Tier 2")) or None,
                tier_3=_clean(row.get("Tier 3")) or None,
            )
    return entries


def render_iab_taxonomy_for_prompt(path: Path = DEFAULT_IAB_TAXONOMY_PATH) -> str:
    entries = load_iab_taxonomy(path)
    if not entries:
        return "- no IAB product taxonomy file found"
    lines: list[str] = []
    for entry in entries.values():
        parent = entry.parent_id or "root"
        lines.append(
            f"- {entry.unique_id} | parent={parent} | depth={entry.selected_depth} | "
            f"{entry.full_path}"
        )
    return "\n".join(lines)


def iab_category_from_id(
    unique_id: str,
    *,
    confidence: str = "medium",
    path: Path = DEFAULT_IAB_TAXONOMY_PATH,
) -> IABCategory | None:
    entries = load_iab_taxonomy(path)
    entry = entries.get(unique_id)
    if entry is None:
        return None
    return IABCategory(
        iab_unique_id=entry.unique_id,
        iab_parent_id=entry.parent_id,
        tier_1=entry.tier_1,
        tier_2=entry.tier_2,
        tier_3=entry.tier_3,
        selected_depth=entry.selected_depth,
        selected_category=entry.selected_category,
        full_path=entry.full_path,
        confidence=confidence,
        parent_categories=_parent_categories(entry, entries),
        alternative_categories=[],
    )


def normalize_iab_category(
    category: IABCategory | dict | None,
    path: Path = DEFAULT_IAB_TAXONOMY_PATH,
) -> IABCategory | None:
    if category is None:
        return None
    if isinstance(category, dict):
        try:
            category = IABCategory.model_validate(category)
        except ValueError:
            return None

    entries = load_iab_taxonomy(path)
    if not entries:
        return category

    entry = entries.get(category.iab_unique_id) or _find_entry(category, entries)
    if entry is None:
        return None

    return IABCategory(
        iab_unique_id=entry.unique_id,
        iab_parent_id=entry.parent_id,
        tier_1=entry.tier_1,
        tier_2=entry.tier_2,
        tier_3=entry.tier_3,
        selected_depth=entry.selected_depth,
        selected_category=entry.selected_category,
        full_path=entry.full_path,
        confidence=category.confidence,
        parent_categories=_parent_categories(entry, entries),
        alternative_categories=_normalize_alternatives(category.alternative_categories, entries),
    )


def infer_iab_category(
    category: IABCategory | dict | None,
    *,
    primary_category: str | None = None,
    subcategory: str | None = None,
    products: list[str] | None = None,
    evidence_texts: list[str] | None = None,
    path: Path = DEFAULT_IAB_TAXONOMY_PATH,
) -> IABCategory | None:
    normalized = normalize_iab_category(category, path)
    blob = _inference_blob(
        [
            primary_category,
            subcategory,
            normalized.full_path if normalized else None,
            *(products or []),
            *(evidence_texts or []),
        ]
    )
    if not _has_skin_care_signal(blob):
        return normalized
    if normalized and normalized.iab_unique_id in {"1244", "1246"}:
        return normalized
    if normalized and normalized.iab_unique_id not in {"1123", "1138"}:
        return normalized
    return iab_category_from_id(
        "1244",
        confidence=normalized.confidence if normalized else "medium",
        path=path,
    )


def _find_entry(
    category: IABCategory,
    entries: dict[str, IABTaxonomyEntry],
) -> IABTaxonomyEntry | None:
    wanted_path = _key(category.full_path)
    wanted_selected = _key(category.selected_category)
    for entry in entries.values():
        if wanted_path and _key(entry.full_path) == wanted_path:
            return entry
        if wanted_selected and _key(entry.selected_category) == wanted_selected:
            return entry
    return None


def _parent_categories(
    entry: IABTaxonomyEntry,
    entries: dict[str, IABTaxonomyEntry],
) -> list[IABCategoryNode]:
    chain: list[IABCategoryNode] = []
    parent_id = entry.parent_id
    seen: set[str] = {entry.unique_id}
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = entries.get(parent_id)
        if parent is None:
            break
        chain.append(
            IABCategoryNode(
                iab_unique_id=parent.unique_id,
                name=parent.selected_category,
                depth=parent.selected_depth,
                full_path=parent.full_path,
            )
        )
        parent_id = parent.parent_id
    return list(reversed(chain))


def _normalize_alternatives(
    alternatives: list[IABAlternativeCategory],
    entries: dict[str, IABTaxonomyEntry],
) -> list[IABAlternativeCategory]:
    normalized: list[IABAlternativeCategory] = []
    for alt in alternatives:
        entry = entries.get(alt.iab_unique_id)
        if entry is None:
            entry = next(
                (
                    candidate
                    for candidate in entries.values()
                    if _key(candidate.full_path) == _key(alt.full_path)
                ),
                None,
            )
        if entry is None:
            continue
        normalized.append(
            IABAlternativeCategory(
                iab_unique_id=entry.unique_id,
                full_path=entry.full_path,
                use_when=alt.use_when,
            )
        )
    return normalized


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _key(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _inference_blob(values: list[str | None]) -> str:
    text = " ".join(value for value in values if value)
    normalized = re.sub(r"[_\-/]+", " ", text.casefold())
    normalized = re.sub(r"[^a-z0-9& ]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _has_skin_care_signal(blob: str) -> bool:
    if not blob:
        return False
    padded = f" {blob} "
    return any(
        f" {term} " in padded
        for term in (
            "skin care",
            "skincare",
            "visible aging",
            "fine lines",
            "moisturizer",
            "moisturiser",
            "facial cream",
            "skin cream",
            "serum",
        )
    )
