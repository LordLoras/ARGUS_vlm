"""Tests for the knowledge module — schema, loader, manager, rules."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ad_classifier.knowledge.loader import (
    seed_default_inference_rules,
)
from ad_classifier.knowledge.manager import KnowledgeManager
from ad_classifier.knowledge.models import (
    BrandCategoryRule,
    CorrectionEntry,
    IABTaxonomyEntry,
    InferenceRule,
    TaxonomyOverride,
)
from ad_classifier.knowledge.schema import initialize_knowledge_db


@pytest.fixture
def kb(tmp_path: Path) -> KnowledgeManager:
    db_path = tmp_path / "test_knowledge.db"
    return KnowledgeManager(db_path)


@pytest.fixture
def loaded_kb(kb: KnowledgeManager) -> KnowledgeManager:
    """Knowledge manager with taxonomies loaded (uses real TSV files if available)."""
    try:
        kb.load_taxonomies()
    except Exception:
        pass
    return kb


class TestSchema:
    def test_creates_db(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        result = initialize_knowledge_db(db_path)
        assert db_path.exists()

    def test_idempotent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        initialize_knowledge_db(db_path)
        initialize_knowledge_db(db_path)
        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        conn.close()
        assert "iab_product_taxonomy" in tables
        assert "iab_content_taxonomy" in tables
        assert "brand_category_rules" in tables
        assert "taxonomy_overrides" in tables
        assert "correction_log" in tables
        assert "inference_rules" in tables
        assert "taxonomy_versions" in tables


class TestKnowledgeManager:
    def test_product_taxonomy_roundtrip(self, loaded_kb: KnowledgeManager) -> None:
        entries = loaded_kb.list_product_taxonomy()
        # If TSV files exist, should have entries; if not, empty is fine
        if not entries:
            pytest.skip("No IAB product TSV file available")
        assert len(entries) > 0
        assert all(isinstance(e, IABTaxonomyEntry) for e in entries)
        # All roots should have no parent_id
        assert all(e.parent_id is None for e in entries)

    def test_content_taxonomy_roundtrip(self, loaded_kb: KnowledgeManager) -> None:
        entries = loaded_kb.list_content_taxonomy()
        if not entries:
            pytest.skip("No IAB content TSV file available")
        assert len(entries) > 0

    def test_search_product(self, loaded_kb: KnowledgeManager) -> None:
        results = loaded_kb.search_product_taxonomy("Beer")
        if not results:
            pytest.skip("No IAB product TSV file available")
        assert any("Beer" in (e.name or "") for e in results)

    def test_search_content(self, loaded_kb: KnowledgeManager) -> None:
        results = loaded_kb.search_content_taxonomy("SUV")
        if not results:
            pytest.skip("No IAB content TSV file available")
        assert any("SUV" in (e.name or "") for e in results)

    def test_get_product_entry(self, loaded_kb: KnowledgeManager) -> None:
        # Try to get a known IAB product entry
        entry = loaded_kb.get_product_entry("1004")  # Beer
        if entry is None:
            pytest.skip("No IAB product TSV file available")
        assert entry.unique_id == "1004"
        assert "Beer" in (entry.name or "")

    def test_toggle_product_active(self, loaded_kb: KnowledgeManager) -> None:
        entry = loaded_kb.get_product_entry("1004")
        if entry is None:
            pytest.skip("No IAB product TSV file available")
        loaded_kb.set_product_entry_active("1004", False)
        deactivated = loaded_kb.get_product_entry("1004")
        assert deactivated is not None
        assert not deactivated.active
        loaded_kb.set_product_entry_active("1004", True)
        reactivated = loaded_kb.get_product_entry("1004")
        assert reactivated is not None
        assert reactivated.active


class TestBrandRules:
    def test_create_and_lookup(self, kb: KnowledgeManager) -> None:
        rule = BrandCategoryRule(
            brand_name="Nike",
            primary_category="cpg_food_beverage",
            iab_product_id="1004",
            source="manual",
        )
        result = kb.upsert_brand_rule(rule)
        assert result.id is not None
        assert result.brand_name == "Nike"

        looked_up = kb.lookup_brand_rule("Nike")
        assert looked_up is not None
        assert looked_up.primary_category == "cpg_food_beverage"
        assert looked_up.iab_product_id == "1004"

    def test_case_insensitive_lookup(self, kb: KnowledgeManager) -> None:
        kb.upsert_brand_rule(BrandCategoryRule(brand_name="Adidas", primary_category="other"))
        assert kb.lookup_brand_rule("adidas") is not None
        assert kb.lookup_brand_rule("ADIDAS") is not None

    def test_delete(self, kb: KnowledgeManager) -> None:
        rule = kb.upsert_brand_rule(BrandCategoryRule(brand_name="Puma", primary_category="other"))
        assert kb.delete_brand_rule(rule.id)
        assert kb.lookup_brand_rule("Puma") is None

    def test_upsert_updates_existing(self, kb: KnowledgeManager) -> None:
        kb.upsert_brand_rule(BrandCategoryRule(
            brand_name="Reebok", primary_category="other", source="manual",
        ))
        kb.upsert_brand_rule(BrandCategoryRule(
            brand_name="Reebok", primary_category="automotive", source="manual",
        ))
        rules = kb.list_brand_rules()
        reebok = [r for r in rules if r.brand_name == "Reebok"]
        assert len(reebok) == 1
        assert reebok[0].primary_category == "automotive"


class TestOverrides:
    def test_create_and_list(self, kb: KnowledgeManager) -> None:
        override = TaxonomyOverride(
            override_type="keyword",
            pattern="pickup truck",
            primary_category="automotive",
            iab_product_id="1028",
        )
        result = kb.upsert_override(override)
        assert result.id is not None

        overrides = kb.list_overrides(override_type="keyword")
        assert len(overrides) == 1
        assert overrides[0].pattern == "pickup truck"

    def test_delete(self, kb: KnowledgeManager) -> None:
        o = kb.upsert_override(TaxonomyOverride(
            override_type="brand", pattern="Test Brand",
        ))
        assert kb.delete_override(o.id)
        assert kb.list_overrides() == []


class TestCorrections:
    def test_record_correction(self, kb: KnowledgeManager) -> None:
        entry = CorrectionEntry(
            ad_id="ad_123",
            field="primary_category",
            old_value="other",
            new_value="automotive",
        )
        result = kb.record_correction(entry)
        assert result.id is not None

        corrections = kb.list_corrections(ad_id="ad_123")
        assert len(corrections) == 1
        assert corrections[0].new_value == "automotive"

    def test_learn_from_correction(self, kb: KnowledgeManager) -> None:
        entry = CorrectionEntry(
            ad_id="ad_456",
            field="primary_category",
            old_value="Toyota",
            new_value="automotive",
        )
        rule = kb.learn_from_correction(entry)
        assert rule is not None
        assert rule.brand_name == "Toyota"
        assert rule.primary_category == "automotive"
        assert rule.source == "correction"


class TestInferenceRules:
    def test_seed_defaults(self, kb: KnowledgeManager) -> None:
        kb.load_taxonomies()
        rules = kb.list_inference_rules()
        assert len(rules) > 0
        # Should have the skincare rule
        skincare = [r for r in rules if r.target_id == "559"]
        assert len(skincare) >= 1

    def test_create_custom_rule(self, kb: KnowledgeManager) -> None:
        rule = InferenceRule(
            taxonomy_type="content",
            target_id="999",
            terms=["custom term 1", "custom term 2"],
            context_terms=["context"],
        )
        result = kb.upsert_inference_rule(rule)
        assert result.id is not None
        assert result.terms == ["custom term 1", "custom term 2"]


class TestStats:
    def test_stats_structure(self, kb: KnowledgeManager) -> None:
        stats = kb.get_stats()
        assert "product_taxonomy" in stats
        assert "content_taxonomy" in stats
        assert "brand_rules" in stats
        assert "overrides" in stats
        assert "inference_rules" in stats
        assert "corrections_logged" in stats
        assert "versions" in stats


class TestPromptRendering:
    def test_renders_product_taxonomy(self, loaded_kb: KnowledgeManager) -> None:
        result = loaded_kb.render_product_taxonomy_for_prompt()
        assert isinstance(result, str)
        if "no IAB product taxonomy loaded" in result:
            pytest.skip("No product taxonomy loaded")
        assert "|" in result

    def test_renders_content_taxonomy(self, loaded_kb: KnowledgeManager) -> None:
        result = loaded_kb.render_content_taxonomy_for_prompt()
        assert isinstance(result, str)
        if "no IAB content taxonomy loaded" in result:
            pytest.skip("No content taxonomy loaded")
        assert "|" in result
