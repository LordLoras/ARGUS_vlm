from __future__ import annotations

from pydantic import BaseModel, Field


class IABTaxonomyEntry(BaseModel):
    unique_id: str
    parent_id: str | None = None
    name: str
    tier_1: str | None = None
    tier_2: str | None = None
    tier_3: str | None = None
    tier_4: str | None = None
    active: bool = True

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
        parts = [self.tier_1, self.tier_2, self.tier_3, self.tier_4]
        return " > ".join(p for p in parts if p)


class BrandCategoryRule(BaseModel):
    id: int | None = None
    brand_name: str
    primary_category: str | None = None
    iab_product_id: str | None = None
    iab_content_ids: list[str] = Field(default_factory=list)
    subcategory: str | None = None
    source: str = "manual"
    confidence: float = 1.0
    priority: int = 0
    active: bool = True
    notes: str | None = None


class TaxonomyOverride(BaseModel):
    id: int | None = None
    override_type: str
    pattern: str
    primary_category: str | None = None
    iab_product_id: str | None = None
    iab_content_ids: list[str] = Field(default_factory=list)
    priority: int = 0
    active: bool = True
    notes: str | None = None


class CorrectionEntry(BaseModel):
    id: int | None = None
    ad_id: str
    field: str
    old_value: str | None = None
    new_value: str | None = None
    source: str = "manual"


class InferenceRule(BaseModel):
    id: int | None = None
    taxonomy_type: str
    target_id: str
    terms: list[str]
    context_terms: list[str] = Field(default_factory=list)
    priority: int = 0
    active: bool = True
    notes: str | None = None


class TaxonomyVersion(BaseModel):
    id: int | None = None
    taxonomy_type: str
    version: str
    source_file: str | None = None
    entries_count: int | None = None
    loaded_at: str | None = None


class BackfillSuggestion(BaseModel):
    ad_id: str
    brand_name: str | None = None
    current_primary_category: str | None = None
    suggested_primary_category: str | None = None
    current_iab_product_id: str | None = None
    suggested_iab_product_id: str | None = None
    current_iab_content_ids: list[str] = Field(default_factory=list)
    suggested_iab_content_ids: list[str] = Field(default_factory=list)
    rule_source: str | None = None
    confidence: float = 1.0
