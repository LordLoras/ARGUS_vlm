"""Backfill analyzer — re-evaluate existing ads against current knowledge rules."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import structlog

from ad_classifier.knowledge.manager import KnowledgeManager
from ad_classifier.knowledge.models import BackfillSuggestion

logger = structlog.get_logger(__name__)


def run_backfill_analysis(
    main_db: sqlite3.Connection,
    knowledge: KnowledgeManager,
    *,
    brand_rules_only: bool = False,
    limit: int = 1000,
) -> list[BackfillSuggestion]:
    """Compare existing ad classifications against knowledge base rules.

    Returns a list of suggestions where the knowledge base disagrees with
    the current classification. Sorted by confidence (highest first).
    """
    main_db.row_factory = sqlite3.Row
    suggestions: list[BackfillSuggestion] = []

    rows = main_db.execute(
        """SELECT id, brand_name, primary_category, iab_unique_id, iab_content_ids
           FROM ads
           WHERE status = 'completed'
           ORDER BY ingested_at DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()

    logger.info("backfill_analysis_started", ads_scanned=len(rows))

    for row in rows:
        ad_id = row["id"]
        brand_name = row["brand_name"]
        current_category = row["primary_category"]
        current_iab_id = row["iab_unique_id"]
        current_content_ids_raw = row["iab_content_ids"]

        # ── Check brand rules ──────────────────────────────
        if brand_name:
            brand_rule = knowledge.lookup_brand_rule(brand_name)
            if brand_rule and brand_rule.active:
                cat_changed = (
                    brand_rule.primary_category
                    and brand_rule.primary_category != current_category
                )
                iab_changed = (
                    brand_rule.iab_product_id
                    and brand_rule.iab_product_id != current_iab_id
                )

                if cat_changed or iab_changed:
                    suggestions.append(BackfillSuggestion(
                        ad_id=ad_id,
                        brand_name=brand_name,
                        current_primary_category=current_category,
                        suggested_primary_category=brand_rule.primary_category,
                        current_iab_product_id=current_iab_id,
                        suggested_iab_product_id=brand_rule.iab_product_id,
                        suggested_iab_content_ids=brand_rule.iab_content_ids,
                        rule_source=f"brand_rule:{brand_name}",
                        confidence=brand_rule.confidence,
                    ))
                    continue

        if brand_rules_only:
            continue

        # ── Check keyword overrides ────────────────────────
        # Not yet implemented — will use taxonomy_overrides with type='keyword'
        # to match against product text and subcategory.

    suggestions.sort(key=lambda s: s.confidence, reverse=True)
    logger.info(
        "backfill_analysis_complete",
        ads_scanned=len(rows),
        suggestions=len(suggestions),
    )
    return suggestions


def apply_suggestion(
    main_db: sqlite3.Connection,
    knowledge: KnowledgeManager,
    suggestion: BackfillSuggestion,
) -> bool:
    """Apply a single backfill suggestion to the main DB.

    Records the change in the correction log.
    """
    updates: dict[str, Any] = {}
    if suggestion.suggested_primary_category:
        updates["primary_category"] = suggestion.suggested_primary_category
    if suggestion.suggested_iab_product_id:
        # For IAB, we need to look up the full taxonomy entry
        entry = knowledge.get_product_entry(suggestion.suggested_iab_product_id)
        if entry:
            updates["iab_unique_id"] = entry.unique_id
            updates["iab_parent_id"] = entry.parent_id
            updates["iab_tier_1"] = entry.tier_1
            updates["iab_tier_2"] = entry.tier_2
            updates["iab_tier_3"] = entry.tier_3
            updates["iab_selected_depth"] = entry.selected_depth
            updates["iab_selected_category"] = entry.selected_category
            updates["iab_full_path"] = entry.full_path

    if not updates:
        return False

    set_clauses = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [suggestion.ad_id]
    main_db.execute(f"UPDATE ads SET {set_clauses} WHERE id = ?", values)

    # Record in correction log
    for field, new_val in updates.items():
        from ad_classifier.knowledge.models import CorrectionEntry

        knowledge.record_correction(CorrectionEntry(
            ad_id=suggestion.ad_id,
            field=field,
            old_value=suggestion.brand_name,
            new_value=str(new_val),
            source="backfill",
        ))

    main_db.commit()
    return True
