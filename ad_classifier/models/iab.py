from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _IABBase(BaseModel):
    model_config = ConfigDict(extra="ignore")


class IABCategoryNode(_IABBase):
    iab_unique_id: str
    name: str
    depth: int = Field(ge=1, le=3)
    full_path: str


class IABAlternativeCategory(_IABBase):
    iab_unique_id: str
    full_path: str
    use_when: str = ""


def _normalize_confidence_value(value: object) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, int | float):
        if value >= 0.75:
            return "high"
        if value >= 0.45:
            return "medium"
        return "low"
    normalized = str(value).strip().lower()
    if normalized in {"high", "medium", "low", "unknown"}:
        return normalized
    return "unknown"


class IABCategory(_IABBase):
    iab_unique_id: str
    iab_parent_id: str | None = None
    tier_1: str | None = None
    tier_2: str | None = None
    tier_3: str | None = None
    selected_depth: int = Field(ge=1, le=3)
    selected_category: str
    full_path: str
    confidence: str = "unknown"
    parent_categories: list[IABCategoryNode] = Field(default_factory=list)
    alternative_categories: list[IABAlternativeCategory] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: object) -> str:
        return _normalize_confidence_value(value)


class IABContentCategoryNode(_IABBase):
    iab_unique_id: str
    name: str
    depth: int = Field(ge=1, le=4)
    full_path: str


class IABContentCategory(_IABBase):
    iab_unique_id: str
    iab_parent_id: str | None = None
    tier_1: str | None = None
    tier_2: str | None = None
    tier_3: str | None = None
    tier_4: str | None = None
    selected_depth: int = Field(ge=1, le=4)
    selected_category: str
    full_path: str
    confidence: str = "unknown"
    reason: str = ""
    parent_categories: list[IABContentCategoryNode] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalize_confidence(cls, value: object) -> str:
        return _normalize_confidence_value(value)
