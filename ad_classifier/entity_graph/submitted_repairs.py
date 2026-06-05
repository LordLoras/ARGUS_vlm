from __future__ import annotations

from pathlib import Path

from ad_classifier.db.connection import open_database
from ad_classifier.entity_graph.crawler_config import SubmittedDbRepairConfig
from ad_classifier.entity_graph.models import AdChangeSuggestion

FIELD_TO_COLUMN = {
    "ads.brand_name": "brand_name",
    "ads.products_text": "products_text",
    "ads.primary_category": "primary_category",
    "ads.subcategory": "subcategory",
}


class SubmittedAdRepairRepository:
    def __init__(self, db_path: Path, config: SubmittedDbRepairConfig) -> None:
        self.db_path = db_path.expanduser().resolve()
        self.config = config

    def apply_suggestion(self, suggestion: AdChangeSuggestion, *, value: str | None = None) -> str:
        if not self.config.enabled:
            raise PermissionError("submitted DB repairs are disabled in entity_crawler.yaml")
        if suggestion.status != "approved":
            raise PermissionError("suggestion must be approved before it can be applied")
        if suggestion.field_path not in set(self.config.allowed_fields):
            raise PermissionError(f"field is not allowed for submitted DB repair: {suggestion.field_path}")
        column = FIELD_TO_COLUMN.get(suggestion.field_path)
        if column is None:
            raise PermissionError(f"unsupported submitted DB repair field: {suggestion.field_path}")
        next_value = (value if value is not None else suggestion.suggested_value).strip()
        if not next_value:
            raise ValueError("submitted DB repair value is empty")

        conn = open_database(self.db_path)
        try:
            existing = conn.execute(
                "SELECT id FROM ads WHERE id = ?",
                (suggestion.ad_id,),
            ).fetchone()
            if existing is None:
                raise KeyError(suggestion.ad_id)
            conn.execute(
                f"UPDATE ads SET {column} = ? WHERE id = ?",
                (next_value, suggestion.ad_id),
            )
            conn.commit()
            return next_value
        finally:
            conn.close()
