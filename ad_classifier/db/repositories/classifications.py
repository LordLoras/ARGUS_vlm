from __future__ import annotations

import json
import sqlite3

from ad_classifier.db.repositories.base import db_value, row_to_dict
from ad_classifier.models.classification import ClassificationRecord, OCRQuality


def _to_record(row: sqlite3.Row) -> ClassificationRecord:
    data = row_to_dict(row)
    assert data is not None

    data["risk_labels"] = json.loads(data.get("risk_labels_json") or "[]")
    data["evidence"] = json.loads(data.get("evidence_json") or "[]")
    data["vlm_raw"] = json.loads(data.get("vlm_raw_json") or "{}")

    ocr_raw = data.get("ocr_quality_json")
    if ocr_raw:
        ocr_dict = json.loads(ocr_raw)
        data["ocr_quality"] = OCRQuality.model_validate(ocr_dict) if ocr_dict else None
    else:
        data["ocr_quality"] = None

    # Drop raw JSON columns — not in model
    for key in ("risk_labels_json", "evidence_json", "vlm_raw_json", "ocr_quality_json"):
        data.pop(key, None)

    return ClassificationRecord.model_validate(data)


class ClassificationRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, record: ClassificationRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO classifications (
              ad_id, primary_category, risk_labels_json, confidence, decision,
              needs_human_review, ocr_quality_json, vlm_raw_json, evidence_json,
              vlm_model, vlm_prompt_version, embedder_text_model, embedder_visual_model,
              pipeline_version, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ad_id) DO UPDATE SET
              primary_category = excluded.primary_category,
              risk_labels_json = excluded.risk_labels_json,
              confidence = excluded.confidence,
              decision = excluded.decision,
              needs_human_review = excluded.needs_human_review,
              ocr_quality_json = excluded.ocr_quality_json,
              vlm_raw_json = excluded.vlm_raw_json,
              evidence_json = excluded.evidence_json,
              vlm_model = excluded.vlm_model,
              vlm_prompt_version = excluded.vlm_prompt_version,
              embedder_text_model = excluded.embedder_text_model,
              embedder_visual_model = excluded.embedder_visual_model,
              pipeline_version = excluded.pipeline_version,
              created_at = excluded.created_at
            """,
            (
                record.ad_id,
                record.primary_category,
                json.dumps(record.risk_labels),
                record.confidence,
                record.decision,
                db_value(record.needs_human_review),
                json.dumps(record.ocr_quality.model_dump() if record.ocr_quality else None),
                json.dumps(record.vlm_raw),
                json.dumps([e.model_dump() for e in record.evidence]),
                record.vlm_model,
                record.vlm_prompt_version,
                record.embedder_text_model,
                record.embedder_visual_model,
                record.pipeline_version,
                db_value(record.created_at),
            ),
        )

    def get(self, ad_id: str) -> ClassificationRecord | None:
        row = self.conn.execute(
            "SELECT * FROM classifications WHERE ad_id = ?", (ad_id,)
        ).fetchone()
        if row is None:
            return None
        return _to_record(row)

    def delete(self, ad_id: str) -> None:
        self.conn.execute("DELETE FROM classifications WHERE ad_id = ?", (ad_id,))
