"""KnowledgeManager — central API for taxonomy lookups, rules, and corrections."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import structlog

from ad_classifier.knowledge.loader import (
    DEFAULT_IAB_CONTENT_PATH,
    DEFAULT_IAB_PRODUCT_PATH,
    load_content_taxonomy,
    load_product_taxonomy,
    seed_default_inference_rules,
)
from ad_classifier.knowledge.models import (
    BrandCategoryRule,
    CorrectionEntry,
    IABTaxonomyEntry,
    InferenceRule,
    TaxonomyOverride,
)
from ad_classifier.knowledge.schema import initialize_knowledge_db

logger = structlog.get_logger(__name__)

DEFAULT_KB_PATH = Path("./knowledge.db")


class KnowledgeManager:
    def __init__(self, db_path: Path = DEFAULT_KB_PATH) -> None:
        self._db_path = db_path.expanduser().resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        initialize_knowledge_db(self._db_path)

    @contextmanager
    def _connect(self, readonly: bool = False) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if readonly:
            conn.execute("PRAGMA query_only = ON")
        try:
            yield conn
        finally:
            conn.close()

    # ── Initialization ──────────────────────────────────────

    def load_taxonomies(
        self,
        product_tsv: Path = DEFAULT_IAB_PRODUCT_PATH,
        content_tsv: Path = DEFAULT_IAB_CONTENT_PATH,
    ) -> dict[str, int]:
        """Load both IAB taxonomies and seed default rules. Returns counts."""
        with self._connect() as conn:
            product_count = load_product_taxonomy(conn, product_tsv)
            content_count = load_content_taxonomy(conn, content_tsv)
            rules_count = seed_default_inference_rules(conn)
        return {
            "product_entries": product_count,
            "content_entries": content_count,
            "inference_rules": rules_count,
        }

    # ── Product Taxonomy ────────────────────────────────────

    def get_product_entry(self, unique_id: str) -> IABTaxonomyEntry | None:
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                "SELECT * FROM iab_product_taxonomy WHERE unique_id = ?",
                (unique_id,),
            ).fetchone()
            return _row_to_product_entry(row) if row else None

    def list_product_taxonomy(
        self,
        *,
        parent_id: str | None = None,
        active_only: bool = True,
        tier_1: str | None = None,
        roots_only: bool = True,
    ) -> list[IABTaxonomyEntry]:
        with self._connect(readonly=True) as conn:
            clauses: list[str] = []
            params: list[Any] = []
            if active_only:
                clauses.append("active = 1")
            if parent_id is not None:
                clauses.append("parent_id = ?")
                params.append(parent_id)
            elif roots_only and parent_id is None and not tier_1:
                clauses.append("parent_id IS NULL")
            if tier_1 is not None:
                clauses.append("tier_1 = ?")
                params.append(tier_1)

            where = " AND ".join(clauses) if clauses else "1=1"
            rows = conn.execute(
                f"SELECT * FROM iab_product_taxonomy WHERE {where} ORDER BY unique_id",
                params,
            ).fetchall()
            return [_row_to_product_entry(r) for r in rows]

    def search_product_taxonomy(self, query: str, limit: int = 20) -> list[IABTaxonomyEntry]:
        with self._connect(readonly=True) as conn:
            like = f"%{query}%"
            rows = conn.execute(
                """SELECT * FROM iab_product_taxonomy
                   WHERE active = 1 AND (name LIKE ? OR tier_1 LIKE ? OR tier_2 LIKE ? OR tier_3 LIKE ?)
                   ORDER BY unique_id LIMIT ?""",
                (like, like, like, like, limit),
            ).fetchall()
            return [_row_to_product_entry(r) for r in rows]

    def set_product_entry_active(self, unique_id: str, active: bool) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE iab_product_taxonomy SET active = ?, updated_at = datetime('now') WHERE unique_id = ?",
                (int(active), unique_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ── Content Taxonomy ────────────────────────────────────

    def get_content_entry(self, unique_id: str) -> IABTaxonomyEntry | None:
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                "SELECT * FROM iab_content_taxonomy WHERE unique_id = ?",
                (unique_id,),
            ).fetchone()
            return _row_to_content_entry(row) if row else None

    def list_content_taxonomy(
        self,
        *,
        parent_id: str | None = None,
        active_only: bool = True,
        tier_1: str | None = None,
        roots_only: bool = True,
    ) -> list[IABTaxonomyEntry]:
        with self._connect(readonly=True) as conn:
            clauses: list[str] = []
            params: list[Any] = []
            if active_only:
                clauses.append("active = 1")
            if parent_id is not None:
                clauses.append("parent_id = ?")
                params.append(parent_id)
            elif roots_only and parent_id is None and not tier_1:
                clauses.append("parent_id IS NULL")
            if tier_1 is not None:
                clauses.append("tier_1 = ?")
                params.append(tier_1)

            where = " AND ".join(clauses) if clauses else "1=1"
            rows = conn.execute(
                f"SELECT * FROM iab_content_taxonomy WHERE {where} ORDER BY unique_id",
                params,
            ).fetchall()
            return [_row_to_content_entry(r) for r in rows]

    def search_content_taxonomy(self, query: str, limit: int = 20) -> list[IABTaxonomyEntry]:
        with self._connect(readonly=True) as conn:
            like = f"%{query}%"
            rows = conn.execute(
                """SELECT * FROM iab_content_taxonomy
                   WHERE active = 1 AND (name LIKE ? OR tier_1 LIKE ? OR tier_2 LIKE ? OR tier_3 LIKE ? OR tier_4 LIKE ?)
                   ORDER BY unique_id LIMIT ?""",
                (like, like, like, like, like, limit),
            ).fetchall()
            return [_row_to_content_entry(r) for r in rows]

    def set_content_entry_active(self, unique_id: str, active: bool) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE iab_content_taxonomy SET active = ?, updated_at = datetime('now') WHERE unique_id = ?",
                (int(active), unique_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ── Brand Category Rules ────────────────────────────────

    def lookup_brand_rule(self, brand_name: str) -> BrandCategoryRule | None:
        if not brand_name:
            return None
        normalized = brand_name.strip().lower()
        with self._connect(readonly=True) as conn:
            row = conn.execute(
                """SELECT * FROM brand_category_rules
                   WHERE LOWER(brand_name) = ? AND active = 1
                   ORDER BY priority DESC, confidence DESC LIMIT 1""",
                (normalized,),
            ).fetchone()
            return _row_to_brand_rule(row) if row else None

    def list_brand_rules(self, *, active_only: bool = True) -> list[BrandCategoryRule]:
        with self._connect(readonly=True) as conn:
            where = "active = 1" if active_only else "1=1"
            rows = conn.execute(
                f"SELECT * FROM brand_category_rules WHERE {where} ORDER BY brand_name"
            ).fetchall()
            return [_row_to_brand_rule(r) for r in rows]

    def upsert_brand_rule(self, rule: BrandCategoryRule) -> BrandCategoryRule:
        with self._connect() as conn:
            content_ids_json = json.dumps(rule.iab_content_ids)
            conn.execute(
                """INSERT INTO brand_category_rules
                   (brand_name, primary_category, iab_product_id, iab_content_ids,
                    subcategory, source, confidence, priority, active, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(brand_name, source) DO UPDATE SET
                       primary_category=excluded.primary_category,
                       iab_product_id=excluded.iab_product_id,
                       iab_content_ids=excluded.iab_content_ids,
                       subcategory=excluded.subcategory,
                       confidence=excluded.confidence,
                       priority=excluded.priority,
                       active=excluded.active,
                       notes=excluded.notes,
                       updated_at=datetime('now')""",
                (
                    rule.brand_name.strip(),
                    rule.primary_category,
                    rule.iab_product_id,
                    content_ids_json,
                    rule.subcategory,
                    rule.source,
                    rule.confidence,
                    rule.priority,
                    int(rule.active),
                    rule.notes,
                ),
            )
            conn.commit()
            row = conn.execute(
                """SELECT * FROM brand_category_rules
                   WHERE brand_name = ? AND source = ?
                   ORDER BY id DESC LIMIT 1""",
                (rule.brand_name.strip(), rule.source),
            ).fetchone()
            return _row_to_brand_rule(row)

    def delete_brand_rule(self, rule_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM brand_category_rules WHERE id = ?", (rule_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ── Taxonomy Overrides ──────────────────────────────────

    def list_overrides(
        self,
        *,
        override_type: str | None = None,
        active_only: bool = False,
    ) -> list[TaxonomyOverride]:
        with self._connect(readonly=True) as conn:
            clauses: list[str] = []
            params: list[Any] = []
            if override_type:
                clauses.append("override_type = ?")
                params.append(override_type)
            if active_only:
                clauses.append("active = 1")
            where = " AND ".join(clauses) if clauses else "1=1"
            rows = conn.execute(
                f"""SELECT * FROM taxonomy_overrides
                    WHERE {where}
                    ORDER BY priority DESC, override_type, pattern""",
                params,
            ).fetchall()
            return [_row_to_override(r) for r in rows]

    def upsert_override(self, override: TaxonomyOverride) -> TaxonomyOverride:
        with self._connect() as conn:
            content_ids_json = json.dumps(override.iab_content_ids)
            conn.execute(
                """INSERT INTO taxonomy_overrides
                   (override_type, pattern, primary_category, iab_product_id,
                    iab_content_ids, priority, active, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(override_type, pattern) DO UPDATE SET
                       primary_category=excluded.primary_category,
                       iab_product_id=excluded.iab_product_id,
                       iab_content_ids=excluded.iab_content_ids,
                       priority=excluded.priority,
                       active=excluded.active,
                       notes=excluded.notes,
                       updated_at=datetime('now')""",
                (
                    override.override_type,
                    override.pattern,
                    override.primary_category,
                    override.iab_product_id,
                    content_ids_json,
                    override.priority,
                    int(override.active),
                    override.notes,
                ),
            )
            conn.commit()
            row = conn.execute(
                """SELECT * FROM taxonomy_overrides
                   WHERE override_type = ? AND pattern = ?""",
                (override.override_type, override.pattern),
            ).fetchone()
            return _row_to_override(row)

    def delete_override(self, override_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM taxonomy_overrides WHERE id = ?", (override_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ── Inference Rules ─────────────────────────────────────

    def list_inference_rules(
        self, *, taxonomy_type: str | None = None, active_only: bool = True,
    ) -> list[InferenceRule]:
        with self._connect(readonly=True) as conn:
            clauses: list[str] = []
            params: list[Any] = []
            if active_only:
                clauses.append("active = 1")
            if taxonomy_type:
                clauses.append("taxonomy_type = ?")
                params.append(taxonomy_type)
            where = " AND ".join(clauses) if clauses else "1=1"
            rows = conn.execute(
                f"""SELECT * FROM inference_rules
                    WHERE {where}
                    ORDER BY taxonomy_type, priority DESC, target_id""",
                params,
            ).fetchall()
            return [_row_to_inference_rule(r) for r in rows]

    def upsert_inference_rule(self, rule: InferenceRule) -> InferenceRule:
        with self._connect() as conn:
            terms_json = json.dumps(rule.terms)
            context_json = json.dumps(rule.context_terms)
            conn.execute(
                """INSERT INTO inference_rules
                   (taxonomy_type, target_id, terms, context_terms, priority, active, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule.taxonomy_type,
                    rule.target_id,
                    terms_json,
                    context_json,
                    rule.priority,
                    int(rule.active),
                    rule.notes,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM inference_rules ORDER BY id DESC LIMIT 1",
            ).fetchone()
            return _row_to_inference_rule(row)

    def delete_inference_rule(self, rule_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM inference_rules WHERE id = ?", (rule_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ── Corrections ─────────────────────────────────────────

    def record_correction(self, entry: CorrectionEntry) -> CorrectionEntry:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO correction_log (ad_id, field, old_value, new_value, source)
                   VALUES (?, ?, ?, ?, ?)""",
                (entry.ad_id, entry.field, entry.old_value, entry.new_value, entry.source),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM correction_log ORDER BY id DESC LIMIT 1").fetchone()
            return _row_to_correction(row)

    def list_corrections(
        self, *, ad_id: str | None = None, limit: int = 50,
    ) -> list[CorrectionEntry]:
        with self._connect(readonly=True) as conn:
            if ad_id:
                rows = conn.execute(
                    "SELECT * FROM correction_log WHERE ad_id = ? ORDER BY id DESC LIMIT ?",
                    (ad_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM correction_log ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [_row_to_correction(r) for r in rows]

    def learn_from_correction(self, entry: CorrectionEntry) -> BrandCategoryRule | None:
        """Learn a brand→category rule from a manual correction.

        When a user corrects primary_category or iab_product_id for an ad with a
        known brand, creates/updates a brand_category_rule so future ads with the
        same brand auto-classify correctly.
        """
        if entry.field not in (
            "primary_category",
            "iab_product_id",
            "iab_content_ids",
            "subcategory",
        ) or not entry.new_value:
            return None

        # We need the brand from the ad — caller should set old_value to the brand name
        # when recording the correction for this learning to work.
        brand_name = entry.old_value
        if not brand_name:
            return None

        existing = self.lookup_brand_rule(brand_name)
        rule = existing.model_copy(update={"source": "correction"}) if existing else BrandCategoryRule(
            brand_name=brand_name,
            source="correction",
            confidence=0.9,
            priority=5,
        )
        if entry.field == "primary_category":
            rule.primary_category = entry.new_value
        elif entry.field == "iab_product_id":
            rule.iab_product_id = entry.new_value
        elif entry.field == "iab_content_ids":
            rule.iab_content_ids = [
                item.strip() for item in entry.new_value.split(",") if item.strip()
            ]
        elif entry.field == "subcategory":
            rule.subcategory = entry.new_value

        return self.upsert_brand_rule(rule)

    # ── Prompt Rendering ────────────────────────────────────

    def render_product_taxonomy_for_prompt(self) -> str:
        """Render active IAB product taxonomy entries for VLM prompt injection."""
        with self._connect(readonly=True) as conn:
            rows = conn.execute(
                "SELECT * FROM iab_product_taxonomy WHERE active = 1 ORDER BY unique_id"
            ).fetchall()
            if not rows:
                return "- no IAB product taxonomy loaded"
            lines: list[str] = []
            for row in rows:
                entry = _row_to_product_entry(row)
                parent = entry.parent_id or "root"
                lines.append(
                    f"- {entry.unique_id} | parent={parent} | depth={entry.selected_depth} | "
                    f"{entry.full_path}"
                )
            return "\n".join(lines)

    def render_content_taxonomy_for_prompt(self) -> str:
        """Render active IAB content taxonomy entries for VLM prompt injection."""
        with self._connect(readonly=True) as conn:
            rows = conn.execute(
                "SELECT * FROM iab_content_taxonomy WHERE active = 1 ORDER BY unique_id"
            ).fetchall()
            if not rows:
                return "- no IAB content taxonomy loaded"
            lines: list[str] = []
            for row in rows:
                entry = _row_to_content_entry(row)
                parent = entry.parent_id or "root"
                lines.append(
                    f"- {entry.unique_id} | parent={parent} | depth={entry.selected_depth} | "
                    f"{entry.full_path}"
                )
            return "\n".join(lines)

    def render_runtime_guidance_for_prompt(self, *, limit: int = 80) -> str:
        """Render editable knowledge rules as concise VLM guidance."""
        with self._connect(readonly=True) as conn:
            lines: list[str] = []
            brand_rows = conn.execute(
                """SELECT * FROM brand_category_rules
                   WHERE active = 1
                   ORDER BY priority DESC, confidence DESC, brand_name
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            for row in brand_rows:
                rule = _row_to_brand_rule(row)
                lines.append(
                    "- brand_rule | "
                    f"brand={rule.brand_name} | primary={rule.primary_category or '-'} | "
                    f"product_iab={rule.iab_product_id or '-'} | "
                    f"content_iab={','.join(rule.iab_content_ids) or '-'} | "
                    f"subcategory={rule.subcategory or '-'}"
                )

            remaining = max(0, limit - len(lines))
            if remaining:
                override_rows = conn.execute(
                    """SELECT * FROM taxonomy_overrides
                       WHERE active = 1
                       ORDER BY priority DESC, override_type, pattern
                       LIMIT ?""",
                    (remaining,),
                ).fetchall()
                for row in override_rows:
                    override = _row_to_override(row)
                    lines.append(
                        "- override | "
                        f"type={override.override_type} | pattern={override.pattern} | "
                        f"primary={override.primary_category or '-'} | "
                        f"product_iab={override.iab_product_id or '-'} | "
                        f"content_iab={','.join(override.iab_content_ids) or '-'}"
                    )

            remaining = max(0, limit - len(lines))
            if remaining:
                inference_rows = conn.execute(
                    """SELECT * FROM inference_rules
                       WHERE active = 1
                       ORDER BY taxonomy_type, priority DESC, target_id
                       LIMIT ?""",
                    (remaining,),
                ).fetchall()
                for row in inference_rows:
                    rule = _row_to_inference_rule(row)
                    lines.append(
                        "- inference | "
                        f"type={rule.taxonomy_type} | target_iab={rule.target_id} | "
                        f"terms={', '.join(rule.terms[:8])} | "
                        f"context={', '.join(rule.context_terms[:6]) or '-'}"
                    )

            return "\n".join(lines) if lines else "- no editable taxonomy rules configured"

    # ── Stats ───────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        with self._connect(readonly=True) as conn:
            product_total = conn.execute("SELECT COUNT(*) FROM iab_product_taxonomy").fetchone()[0]
            product_active = conn.execute(
                "SELECT COUNT(*) FROM iab_product_taxonomy WHERE active = 1"
            ).fetchone()[0]
            content_total = conn.execute("SELECT COUNT(*) FROM iab_content_taxonomy").fetchone()[0]
            content_active = conn.execute(
                "SELECT COUNT(*) FROM iab_content_taxonomy WHERE active = 1"
            ).fetchone()[0]
            brand_rules = conn.execute(
                "SELECT COUNT(*) FROM brand_category_rules WHERE active = 1"
            ).fetchone()[0]
            overrides = conn.execute(
                "SELECT COUNT(*) FROM taxonomy_overrides WHERE active = 1"
            ).fetchone()[0]
            inference_rules = conn.execute(
                "SELECT COUNT(*) FROM inference_rules WHERE active = 1"
            ).fetchone()[0]
            corrections = conn.execute("SELECT COUNT(*) FROM correction_log").fetchone()[0]

            versions: list[dict] = []
            for row in conn.execute("SELECT * FROM taxonomy_versions ORDER BY taxonomy_type").fetchall():
                versions.append({
                    "taxonomy_type": row["taxonomy_type"],
                    "version": row["version"],
                    "entries_count": row["entries_count"],
                    "loaded_at": row["loaded_at"],
                })

        return {
            "product_taxonomy": {"total": product_total, "active": product_active},
            "content_taxonomy": {"total": content_total, "active": content_active},
            "brand_rules": brand_rules,
            "overrides": overrides,
            "inference_rules": inference_rules,
            "corrections_logged": corrections,
            "versions": versions,
        }


# ── Row-to-model helpers ────────────────────────────────────


def _row_to_product_entry(row: sqlite3.Row) -> IABTaxonomyEntry:
    return IABTaxonomyEntry(
        unique_id=row["unique_id"],
        parent_id=row["parent_id"],
        name=row["name"],
        tier_1=row["tier_1"],
        tier_2=row["tier_2"],
        tier_3=row["tier_3"],
        tier_4=None,
        active=bool(row["active"]),
    )


def _row_to_content_entry(row: sqlite3.Row) -> IABTaxonomyEntry:
    return IABTaxonomyEntry(
        unique_id=row["unique_id"],
        parent_id=row["parent_id"],
        name=row["name"],
        tier_1=row["tier_1"],
        tier_2=row["tier_2"],
        tier_3=row["tier_3"],
        tier_4=row["tier_4"],
        active=bool(row["active"]),
    )


def _row_to_brand_rule(row: sqlite3.Row) -> BrandCategoryRule:
    content_ids_raw = row["iab_content_ids"] or "[]"
    return BrandCategoryRule(
        id=row["id"],
        brand_name=row["brand_name"],
        primary_category=row["primary_category"],
        iab_product_id=row["iab_product_id"],
        iab_content_ids=json.loads(content_ids_raw) if isinstance(content_ids_raw, str) else [],
        subcategory=row["subcategory"],
        source=row["source"],
        confidence=row["confidence"],
        priority=row["priority"],
        active=bool(row["active"]),
        notes=row["notes"],
    )


def _row_to_override(row: sqlite3.Row) -> TaxonomyOverride:
    content_ids_raw = row["iab_content_ids"] or "[]"
    return TaxonomyOverride(
        id=row["id"],
        override_type=row["override_type"],
        pattern=row["pattern"],
        primary_category=row["primary_category"],
        iab_product_id=row["iab_product_id"],
        iab_content_ids=json.loads(content_ids_raw) if isinstance(content_ids_raw, str) else [],
        priority=row["priority"],
        active=bool(row["active"]),
        notes=row["notes"],
    )


def _row_to_inference_rule(row: sqlite3.Row) -> InferenceRule:
    terms_raw = row["terms"] or "[]"
    context_raw = row["context_terms"] or "[]"
    return InferenceRule(
        id=row["id"],
        taxonomy_type=row["taxonomy_type"],
        target_id=row["target_id"],
        terms=json.loads(terms_raw) if isinstance(terms_raw, str) else [],
        context_terms=json.loads(context_raw) if isinstance(context_raw, str) else [],
        priority=row["priority"],
        active=bool(row["active"]),
        notes=row["notes"],
    )


def _row_to_correction(row: sqlite3.Row) -> CorrectionEntry:
    return CorrectionEntry(
        id=row["id"],
        ad_id=row["ad_id"],
        field=row["field"],
        old_value=row["old_value"],
        new_value=row["new_value"],
        source=row["source"],
    )
