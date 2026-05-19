"""Runtime application of editable taxonomy knowledge.

The knowledge DB is user-editable, so runtime classification needs to treat it as
the authoritative overlay on top of the older TSV-backed helpers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ad_classifier.brand_profiles.matching import normalize_profile_name, unique
from ad_classifier.iab_content_taxonomy import infer_iab_content_categories
from ad_classifier.iab_taxonomy import infer_iab_category
from ad_classifier.knowledge.models import IABTaxonomyEntry, InferenceRule, TaxonomyOverride
from ad_classifier.models.iab import (
    IABCategory,
    IABCategoryNode,
    IABContentCategory,
    IABContentCategoryNode,
)

if TYPE_CHECKING:
    from ad_classifier.knowledge.manager import KnowledgeManager
    from ad_classifier.models.marketing import MarketingEntities


_BROAD_PRODUCT_IDS = {"1123", "1138"}
_INCIDENTAL_MUSIC_RE = re.compile(
    r"\b(?:background|incidental|generic|theme|soundtrack|score)\s+music\b|"
    r"\bmusic\s+(?:plays|bed|under|underneath)\b",
    re.IGNORECASE,
)
_INCIDENTAL_ANIMATION_RE = re.compile(
    r"\banimated\s+(?:graphics|logo|text|background|transition|card|bumper)s?\b|"
    r"\banimation\s+(?:style|effect|graphics)\b",
    re.IGNORECASE,
)
_STRONG_CONTENT_TERMS: dict[str, frozenset[str]] = {
    "338": frozenset(
        {
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
        }
    ),
    "641": frozenset({"anime", "manga", "cartoon"}),
}


@dataclass
class KnowledgeApplication:
    primary_category: str
    subcategory: str | None
    iab_category: IABCategory | None
    iab_content_categories: list[IABContentCategory]
    debug_events: list[dict[str, str]] = field(default_factory=list)


def apply_runtime_knowledge(
    knowledge: KnowledgeManager | None,
    *,
    primary_category: str,
    marketing_entities: MarketingEntities,
    iab_category: IABCategory | None,
    iab_content_categories: list[IABContentCategory],
    evidence_texts: list[str],
) -> KnowledgeApplication:
    if knowledge is None:
        return KnowledgeApplication(
            primary_category=primary_category,
            subcategory=marketing_entities.subcategory,
            iab_category=iab_category,
            iab_content_categories=iab_content_categories,
        )

    debug_events: list[dict[str, str]] = []
    category = primary_category
    subcategory = marketing_entities.subcategory
    iab_category = normalize_product_category(knowledge, iab_category, debug_events=debug_events)
    iab_content_categories = normalize_content_categories(
        knowledge,
        iab_content_categories,
        debug_events=debug_events,
    )

    brand_names = _brand_candidates(marketing_entities)
    rule = next(
        (
            found
            for brand in brand_names
            if (found := knowledge.lookup_brand_rule(brand)) is not None
        ),
        None,
    )
    if rule is not None:
        if rule.primary_category:
            category = rule.primary_category
        if rule.subcategory:
            subcategory = rule.subcategory
            marketing_entities.subcategory = rule.subcategory
        if rule.iab_product_id:
            replacement = product_category_from_id(
                knowledge,
                rule.iab_product_id,
                confidence=_confidence_label(rule.confidence),
            )
            if replacement is not None:
                iab_category = replacement
        if rule.iab_content_ids:
            replacement_content = content_categories_from_ids(
                knowledge,
                rule.iab_content_ids,
                confidence=_confidence_label(rule.confidence),
                reason=f"Brand rule matched {rule.brand_name}",
            )
            if replacement_content:
                iab_content_categories = replacement_content
        debug_events.append(
            {
                "source": "brand_rule",
                "brand": rule.brand_name,
                "message": "applied editable brand taxonomy rule",
            }
        )

    blob = _rule_blob(
        [
            category,
            subcategory,
            iab_category.full_path if iab_category else None,
            *marketing_entities.products,
            *evidence_texts,
        ]
    )

    category, iab_category, iab_content_categories = _apply_overrides(
        knowledge,
        category=category,
        iab_category=iab_category,
        iab_content_categories=iab_content_categories,
        marketing_entities=marketing_entities,
        evidence_blob=blob,
        debug_events=debug_events,
    )
    iab_category, iab_content_categories = _apply_inference_rules(
        knowledge,
        iab_category=iab_category,
        iab_content_categories=iab_content_categories,
        category=category,
        subcategory=subcategory,
        marketing_entities=marketing_entities,
        evidence_blob=blob,
        debug_events=debug_events,
    )

    return KnowledgeApplication(
        primary_category=category,
        subcategory=subcategory,
        iab_category=iab_category,
        iab_content_categories=iab_content_categories,
        debug_events=debug_events,
    )


def product_category_from_id(
    knowledge: KnowledgeManager,
    unique_id: str,
    *,
    confidence: str = "medium",
) -> IABCategory | None:
    entry = knowledge.get_product_entry(unique_id)
    if entry is None or not entry.active:
        return None
    return _product_category_from_entry(knowledge, entry, confidence=confidence)


def content_categories_from_ids(
    knowledge: KnowledgeManager,
    unique_ids: list[str],
    *,
    confidence: str = "medium",
    reason: str = "",
) -> list[IABContentCategory]:
    categories: list[IABContentCategory] = []
    seen: set[str] = set()
    for unique_id in unique_ids:
        if unique_id in seen:
            continue
        entry = knowledge.get_content_entry(unique_id)
        if entry is None or not entry.active:
            continue
        categories.append(_content_category_from_entry(knowledge, entry, confidence, reason))
        seen.add(unique_id)
    return categories


def normalize_product_category(
    knowledge: KnowledgeManager,
    category: IABCategory | None,
    *,
    debug_events: list[dict[str, str]] | None = None,
) -> IABCategory | None:
    if category is None:
        return None
    entry = knowledge.get_product_entry(category.iab_unique_id)
    if entry is None:
        return category
    if not entry.active:
        if debug_events is not None:
            debug_events.append(
                {
                    "source": "taxonomy_active",
                    "target": category.iab_unique_id,
                    "message": "dropped inactive product taxonomy category",
                }
            )
        return None
    return _product_category_from_entry(knowledge, entry, confidence=category.confidence)


def normalize_content_categories(
    knowledge: KnowledgeManager,
    categories: list[IABContentCategory],
    *,
    debug_events: list[dict[str, str]] | None = None,
) -> list[IABContentCategory]:
    normalized: list[IABContentCategory] = []
    seen: set[str] = set()
    for category in categories:
        entry = knowledge.get_content_entry(category.iab_unique_id)
        if entry is None:
            if category.iab_unique_id not in seen:
                normalized.append(category)
                seen.add(category.iab_unique_id)
            continue
        if not entry.active:
            if debug_events is not None:
                debug_events.append(
                    {
                        "source": "taxonomy_active",
                        "target": category.iab_unique_id,
                        "message": "dropped inactive content taxonomy category",
                    }
                )
            continue
        if entry.unique_id in seen:
            continue
        normalized.append(
            _content_category_from_entry(
                knowledge,
                entry,
                confidence=category.confidence,
                reason=category.reason,
            )
        )
        seen.add(entry.unique_id)
    return normalized


def infer_product_with_knowledge(
    knowledge: KnowledgeManager | None,
    category: IABCategory | dict | None,
    *,
    primary_category: str | None = None,
    subcategory: str | None = None,
    products: list[str] | None = None,
    evidence_texts: list[str] | None = None,
) -> IABCategory | None:
    normalized = infer_iab_category(
        category,
        primary_category=primary_category,
        subcategory=subcategory,
        products=products,
        evidence_texts=evidence_texts,
    )
    if knowledge is None:
        return normalized
    return normalize_product_category(knowledge, normalized)


def infer_content_with_knowledge(
    knowledge: KnowledgeManager | None,
    *,
    existing: list[IABContentCategory] | None = None,
    primary_category: str | None = None,
    subcategory: str | None = None,
    products: list[str] | None = None,
    product_iab_path: str | None = None,
    evidence_texts: list[str] | None = None,
) -> list[IABContentCategory]:
    normalized = infer_iab_content_categories(
        existing=existing,
        primary_category=primary_category,
        subcategory=subcategory,
        products=products,
        product_iab_path=product_iab_path,
        evidence_texts=evidence_texts,
    )
    if knowledge is None:
        return normalized
    return normalize_content_categories(knowledge, normalized)


def _apply_overrides(
    knowledge: KnowledgeManager,
    *,
    category: str,
    iab_category: IABCategory | None,
    iab_content_categories: list[IABContentCategory],
    marketing_entities: MarketingEntities,
    evidence_blob: str,
    debug_events: list[dict[str, str]],
) -> tuple[str, IABCategory | None, list[IABContentCategory]]:
    applied_fields: set[str] = set()
    overrides = sorted(
        [override for override in knowledge.list_overrides() if override.active],
        key=lambda override: override.priority,
        reverse=True,
    )
    for override in overrides:
        if not _override_matches(override, marketing_entities, evidence_blob):
            continue
        if override.primary_category and "primary_category" not in applied_fields:
            category = override.primary_category
            applied_fields.add("primary_category")
        if override.iab_product_id and "iab_product_id" not in applied_fields:
            replacement = product_category_from_id(knowledge, override.iab_product_id)
            if replacement is not None:
                iab_category = replacement
                applied_fields.add("iab_product_id")
        if override.iab_content_ids and "iab_content_ids" not in applied_fields:
            replacement_content = content_categories_from_ids(
                knowledge,
                override.iab_content_ids,
                reason=f"Override matched {override.pattern}",
            )
            if replacement_content:
                iab_content_categories = replacement_content
                applied_fields.add("iab_content_ids")
        debug_events.append(
            {
                "source": "taxonomy_override",
                "target": override.pattern,
                "message": f"applied {override.override_type} override",
            }
        )
        if applied_fields == {"primary_category", "iab_product_id", "iab_content_ids"}:
            break
    return category, iab_category, iab_content_categories


def _apply_inference_rules(
    knowledge: KnowledgeManager,
    *,
    iab_category: IABCategory | None,
    iab_content_categories: list[IABContentCategory],
    category: str,
    subcategory: str | None,
    marketing_entities: MarketingEntities,
    evidence_blob: str,
    debug_events: list[dict[str, str]],
) -> tuple[IABCategory | None, list[IABContentCategory]]:
    blob = _rule_blob(
        [
            category,
            subcategory,
            iab_category.full_path if iab_category else None,
            *marketing_entities.products,
            evidence_blob,
        ]
    )
    product_rules = _matched_rules(
        knowledge.list_inference_rules(taxonomy_type="product"),
        blob,
    )
    if product_rules and _can_product_rule_replace(iab_category, product_rules[0]):
        replacement = product_category_from_id(
            knowledge,
            product_rules[0].target_id,
            confidence="medium",
        )
        if replacement is not None:
            iab_category = replacement
            debug_events.append(
                {
                    "source": "inference_rule",
                    "target": product_rules[0].target_id,
                    "message": "applied product inference rule",
                }
            )

    seen = {item.iab_unique_id for item in iab_content_categories}
    for rule in _matched_rules(knowledge.list_inference_rules(taxonomy_type="content"), blob):
        if rule.target_id in seen:
            continue
        matched_terms = _matched_terms(blob, rule.terms)
        if _incidental_content_match(rule.target_id, matched_terms, blob):
            continue
        replacement = content_categories_from_ids(
            knowledge,
            [rule.target_id],
            confidence="medium",
            reason="Knowledge inference matched: " + ", ".join(matched_terms[:3]),
        )
        if replacement:
            iab_content_categories.extend(replacement)
            seen.add(rule.target_id)
            debug_events.append(
                {
                    "source": "inference_rule",
                    "target": rule.target_id,
                    "message": "applied content inference rule",
                }
            )
    return iab_category, iab_content_categories


def _matched_rules(rules: list[InferenceRule], blob: str) -> list[InferenceRule]:
    matched: list[tuple[InferenceRule, int]] = []
    for rule in rules:
        if not rule.active:
            continue
        if rule.context_terms and not _matched_terms(blob, rule.context_terms):
            continue
        terms = _matched_terms(blob, rule.terms)
        if terms:
            matched.append((rule, len(terms)))
    matched.sort(key=lambda item: (item[0].priority, item[1]), reverse=True)
    return [rule for rule, _ in matched]


def _override_matches(
    override: TaxonomyOverride,
    marketing_entities: MarketingEntities,
    evidence_blob: str,
) -> bool:
    pattern = normalize_profile_name(override.pattern)
    if not pattern:
        return False
    brand_blob = _rule_blob(_brand_candidates(marketing_entities))
    product_blob = _rule_blob(marketing_entities.products)
    subcategory_blob = _rule_blob([marketing_entities.subcategory])
    if override.override_type == "brand":
        return pattern in brand_blob
    if override.override_type == "product_text":
        return pattern in product_blob
    if override.override_type == "subcategory":
        return pattern in subcategory_blob
    return pattern in evidence_blob or pattern in product_blob or pattern in subcategory_blob


def _can_product_rule_replace(
    current: IABCategory | None,
    rule: InferenceRule,
) -> bool:
    if current is None:
        return True
    return current.iab_unique_id in _BROAD_PRODUCT_IDS or rule.priority > 0


def _product_category_from_entry(
    knowledge: KnowledgeManager,
    entry: IABTaxonomyEntry,
    *,
    confidence: str,
) -> IABCategory:
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
        parent_categories=[
            IABCategoryNode(
                iab_unique_id=parent.unique_id,
                name=parent.selected_category,
                depth=parent.selected_depth,
                full_path=parent.full_path,
            )
            for parent in _parent_entries(knowledge, entry, taxonomy_type="product")
        ],
    )


def _content_category_from_entry(
    knowledge: KnowledgeManager,
    entry: IABTaxonomyEntry,
    confidence: str,
    reason: str,
) -> IABContentCategory:
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
        parent_categories=[
            IABContentCategoryNode(
                iab_unique_id=parent.unique_id,
                name=parent.selected_category,
                depth=parent.selected_depth,
                full_path=parent.full_path,
            )
            for parent in _parent_entries(knowledge, entry, taxonomy_type="content")
        ],
    )


def _parent_entries(
    knowledge: KnowledgeManager,
    entry: IABTaxonomyEntry,
    *,
    taxonomy_type: str,
) -> list[IABTaxonomyEntry]:
    parents: list[IABTaxonomyEntry] = []
    parent_id = entry.parent_id
    seen = {entry.unique_id}
    while parent_id and parent_id not in seen:
        seen.add(parent_id)
        parent = (
            knowledge.get_product_entry(parent_id)
            if taxonomy_type == "product"
            else knowledge.get_content_entry(parent_id)
        )
        if parent is None:
            break
        parents.append(parent)
        parent_id = parent.parent_id
    return parents


def _brand_candidates(marketing_entities: MarketingEntities) -> list[str]:
    return unique(
        [
            marketing_entities.brand.name,
            marketing_entities.advertiser.brand_name,
            marketing_entities.advertiser.advertiser_name,
        ]
    )


def _rule_blob(values: list[str | None]) -> str:
    return normalize_profile_name(" ".join(value for value in values if value))


def _matched_terms(blob: str, terms: list[str]) -> list[str]:
    matched: list[str] = []
    for term in terms:
        normalized = normalize_profile_name(term)
        if normalized and re.search(rf"(?<![a-z0-9]){re.escape(normalized)}(?![a-z0-9])", blob):
            matched.append(term)
    return matched


def _incidental_content_match(target_id: str, matched_terms: list[str], blob: str) -> bool:
    if target_id == "338" and _INCIDENTAL_MUSIC_RE.search(blob):
        return not any(term in _STRONG_CONTENT_TERMS["338"] for term in matched_terms)
    if target_id == "641" and _INCIDENTAL_ANIMATION_RE.search(blob):
        return not any(term in _STRONG_CONTENT_TERMS["641"] for term in matched_terms)
    return False


def _confidence_label(value: float | None) -> str:
    if value is None:
        return "medium"
    if value >= 0.8:
        return "high"
    if value >= 0.5:
        return "medium"
    return "low"
