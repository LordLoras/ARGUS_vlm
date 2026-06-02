from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ad_classifier.db.connection import open_readonly_database
from ad_classifier.entity_graph.models import RelatedAdSummary, SubmittedAdObservation


class SubmittedAdReadOnlyRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.expanduser().resolve()

    def list_product_observations(self, *, limit: int = 1000) -> list[SubmittedAdObservation]:
        conn = open_readonly_database(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT
                  a.id,
                  a.brand_name,
                  a.advertiser_name,
                  a.products_text,
                  a.primary_category,
                  a.subcategory,
                  a.iab_unique_id,
                  a.iab_selected_category,
                  a.iab_full_path,
                  a.iab_content_ids,
                  a.iab_content_paths,
                  m.brand_json,
                  m.products_json,
                  m.advertiser_json
                FROM ads a
                LEFT JOIN marketing_entities m ON m.ad_id = a.id
                WHERE coalesce(m.products_json, a.products_text, '') <> ''
                ORDER BY a.ingested_at DESC, a.id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            observations: list[SubmittedAdObservation] = []
            for row in rows:
                for product in _products(row):
                    evidence = _best_evidence(conn, row["id"], product)
                    observations.append(
                        SubmittedAdObservation(
                            ad_id=row["id"],
                            product_name=product,
                            brand_name=_brand(row),
                            advertiser_name=_advertiser(row),
                            parent_company=_parent_company(row),
                            primary_category=row["primary_category"],
                            subcategory=row["subcategory"],
                            iab_product_id=row["iab_unique_id"],
                            iab_product_name=row["iab_selected_category"] or row["iab_full_path"],
                            iab_content_ids=_csv(row["iab_content_ids"]),
                            iab_content_names=_content_names(row["iab_content_paths"]),
                            evidence_text=evidence["text"],
                            evidence_source=evidence["source"],
                            time_ms=evidence["time_ms"],
                            frame_index=evidence["frame_index"],
                            confidence=_observation_confidence(row, evidence),
                        )
                    )
            return observations
        finally:
            conn.close()

    def related_ads(self, ad_ids: list[str]) -> list[RelatedAdSummary]:
        if not ad_ids:
            return []
        conn = open_readonly_database(self.db_path)
        try:
            placeholders = ",".join("?" for _ in ad_ids)
            rows = conn.execute(
                f"""
                SELECT id, brand_name, products_text, primary_category, subcategory, ingested_at
                FROM ads
                WHERE id IN ({placeholders})
                ORDER BY ingested_at DESC, id
                """,
                ad_ids,
            ).fetchall()
            return [
                RelatedAdSummary(
                    ad_id=row["id"],
                    brand_name=row["brand_name"],
                    products_text=row["products_text"],
                    primary_category=row["primary_category"],
                    subcategory=row["subcategory"],
                    ingested_at=str(row["ingested_at"]) if row["ingested_at"] else None,
                )
                for row in rows
            ]
        finally:
            conn.close()

    def query_only_enabled(self) -> bool:
        conn = open_readonly_database(self.db_path)
        try:
            return bool(conn.execute("PRAGMA query_only").fetchone()[0])
        finally:
            conn.close()


def _products(row: sqlite3.Row) -> list[str]:
    raw = _loads(row["products_json"])
    if isinstance(raw, list):
        items = [str(item).strip() for item in raw if str(item).strip()]
        if items:
            return _unique(items)
    return _unique([item.strip() for item in (row["products_text"] or "").split(",") if item.strip()])


def _brand(row: sqlite3.Row) -> str | None:
    if row["brand_name"]:
        return str(row["brand_name"])
    brand = _loads(row["brand_json"])
    if isinstance(brand, dict) and brand.get("name"):
        return str(brand["name"])
    return None


def _advertiser(row: sqlite3.Row) -> str | None:
    if row["advertiser_name"]:
        return str(row["advertiser_name"])
    advertiser = _loads(row["advertiser_json"])
    if isinstance(advertiser, dict) and advertiser.get("advertiser_name"):
        return str(advertiser["advertiser_name"])
    return None


def _parent_company(row: sqlite3.Row) -> str | None:
    advertiser = _loads(row["advertiser_json"])
    if isinstance(advertiser, dict) and advertiser.get("parent_company"):
        return str(advertiser["parent_company"])
    return None


def _best_evidence(conn: sqlite3.Connection, ad_id: str, product: str) -> dict[str, Any]:
    pattern = f"%{product}%"
    ocr = conn.execute(
        """
        SELECT f.time_ms, f.frame_index, o.text, o.confidence
        FROM frames f
        JOIN ocr_items o ON o.frame_id = f.id
        WHERE f.ad_id = ? AND o.text LIKE ?
        ORDER BY coalesce(o.confidence, 0) DESC, f.time_ms
        LIMIT 1
        """,
        (ad_id, pattern),
    ).fetchone()
    if ocr:
        return {
            "source": "ocr",
            "text": ocr["text"],
            "time_ms": ocr["time_ms"],
            "frame_index": ocr["frame_index"],
        }
    transcript = conn.execute(
        """
        SELECT start_ms, text, confidence
        FROM transcript_segments
        WHERE ad_id = ? AND text LIKE ?
        ORDER BY coalesce(confidence, 0) DESC, start_ms
        LIMIT 1
        """,
        (ad_id, pattern),
    ).fetchone()
    if transcript:
        return {
            "source": "transcript",
            "text": transcript["text"],
            "time_ms": transcript["start_ms"],
            "frame_index": None,
        }
    return {
        "source": "marketing_entities",
        "text": f"Product extracted from submitted ad record: {product}",
        "time_ms": None,
        "frame_index": None,
    }


def _observation_confidence(row: sqlite3.Row, evidence: dict[str, Any]) -> float:
    if evidence["source"] in {"ocr", "transcript"} and _brand(row):
        return 0.88
    if _brand(row):
        return 0.78
    return 0.52


def _content_names(raw: str | None) -> list[str]:
    if not raw:
        return []
    return _unique([item.strip() for item in raw.split("|") if item.strip()])


def _csv(raw: str | None) -> list[str]:
    return _unique([item.strip() for item in (raw or "").split(",") if item.strip()])


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
