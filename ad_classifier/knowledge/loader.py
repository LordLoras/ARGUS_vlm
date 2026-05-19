"""Load IAB taxonomy TSV files into the knowledge database."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_IAB_PRODUCT_PATH = Path(__file__).parent.parent.parent / "Ad Product Taxonomy 2.0.tsv"
DEFAULT_IAB_CONTENT_PATH = Path(__file__).parent.parent.parent / "Content Taxonomy 3.1.tsv"


def _clean(value: str | None) -> str:
    return (value or "").strip()


def load_product_taxonomy(
    conn: sqlite3.Connection,
    tsv_path: Path = DEFAULT_IAB_PRODUCT_PATH,
    version: str = "2.0",
) -> int:
    """Load IAB Product Taxonomy TSV into knowledge DB. Returns count of entries loaded."""
    tsv_path = tsv_path.expanduser().resolve()
    if not tsv_path.exists():
        logger.warning("iab_product_tsv_not_found", path=str(tsv_path))
        return 0

    rows = _read_product_tsv(tsv_path)
    if not rows:
        return 0

    _upsert_product_rows(conn, rows)
    _record_version(conn, "product", version, str(tsv_path), len(rows))
    conn.commit()
    logger.info("iab_product_taxonomy_loaded", count=len(rows), version=version)
    return len(rows)


def load_content_taxonomy(
    conn: sqlite3.Connection,
    tsv_path: Path = DEFAULT_IAB_CONTENT_PATH,
    version: str = "3.1",
) -> int:
    """Load IAB Content Taxonomy TSV into knowledge DB. Returns count of entries loaded."""
    tsv_path = tsv_path.expanduser().resolve()
    if not tsv_path.exists():
        logger.warning("iab_content_tsv_not_found", path=str(tsv_path))
        return 0

    rows = _read_content_tsv(tsv_path)
    if not rows:
        return 0

    _upsert_content_rows(conn, rows)
    _record_version(conn, "content", version, str(tsv_path), len(rows))
    conn.commit()
    logger.info("iab_content_taxonomy_loaded", count=len(rows), version=version)
    return len(rows)


def seed_default_inference_rules(conn: sqlite3.Connection) -> int:
    """Seed the inference_rules table with rules extracted from the old hardcoded lists.

    Only inserts if the table is empty. Returns count of rules inserted.
    """
    count = conn.execute("SELECT COUNT(*) FROM inference_rules").fetchone()[0]
    if count > 0:
        return 0

    rules = [
        # Content taxonomy — beauty product signals
        ("content", "559", json.dumps([
            "skin care", "skincare", "anti aging", "visible aging", "fine lines",
            "firmness", "radiance", "smoothness", "moisturizer", "moisturiser",
            "serum", "facial cream", "skin cream",
        ]), json.dumps([
            "beauty personal care", "beauty", "cosmetic", "cosmetics",
            "consumer packaged goods", "personal care", "skin care", "skincare",
            "style fashion",
        ]), "Skin Care inference from beauty context"),
        ("content", "558", json.dumps(["perfume", "fragrance", "cologne", "eau de parfum", "eau de toilette"]),
         json.dumps(["beauty personal care", "beauty", "cosmetic", "cosmetics",
                     "consumer packaged goods", "personal care", "skin care", "skincare", "style fashion"]),
         "Fragrance inference from beauty context"),
        ("content", "554", json.dumps(["hair care", "shampoo", "conditioner", "hair serum", "hair color"]),
         json.dumps(["beauty personal care", "beauty", "cosmetic", "cosmetics",
                     "consumer packaged goods", "personal care", "skin care", "skincare", "style fashion"]),
         "Hair Care inference from beauty context"),
        ("content", "555", json.dumps(["makeup", "mascara", "lipstick", "foundation", "concealer", "eyeliner", "blush"]),
         json.dumps(["beauty personal care", "beauty", "cosmetic", "cosmetics",
                     "consumer packaged goods", "personal care", "skin care", "skincare", "style fashion"]),
         "Makeup inference from beauty context"),
        ("content", "556", json.dumps(["nail care", "nail polish", "manicure", "pedicure"]),
         json.dumps(["beauty personal care", "beauty", "cosmetic", "cosmetics",
                     "consumer packaged goods", "personal care", "skin care", "skincare", "style fashion"]),
         "Nail Care inference from beauty context"),
        # Content taxonomy — direct support rules (music, animation)
        ("content", "338", json.dumps([
            "music", "song", "single", "album", "artist", "band", "concert",
            "tour", "playlist", "radio", "dj", "singer", "rapper", "orchestra",
            "music video",
        ]), "", "Music direct content support"),
        ("content", "641", json.dumps(["animation", "animated", "anime", "manga", "cartoon"]),
         "", "Animation & Anime direct content support"),
        # Product taxonomy — skincare fallback
        ("product", "1244", json.dumps([
            "skin care", "skincare", "visible aging", "fine lines", "moisturizer",
            "moisturiser", "facial cream", "skin cream", "serum",
        ]), "", "Skin Care product inference (fallback from broad beauty)"),
    ]

    conn.executemany(
        """INSERT INTO inference_rules
           (taxonomy_type, target_id, terms, context_terms, notes)
           VALUES (?, ?, ?, ?, ?)""",
        rules,
    )
    conn.commit()
    logger.info("inference_rules_seeded", count=len(rules))
    return len(rules)


def _read_product_tsv(path: Path) -> list[dict]:
    entries: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            uid = _clean(row.get("Unique ID"))
            if not uid:
                continue
            entries.append({
                "unique_id": uid,
                "parent_id": _clean(row.get("Parent ID")) or None,
                "name": _clean(row.get("Name")) or uid,
                "tier_1": _clean(row.get("Tier 1")) or None,
                "tier_2": _clean(row.get("Tier 2")) or None,
                "tier_3": _clean(row.get("Tier 3")) or None,
            })
    return entries


def _read_content_tsv(path: Path) -> list[dict]:
    entries: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle, delimiter="\t")
        header: list[str] | None = None
        for row in rows:
            cleaned = [_clean(v) for v in row]
            if cleaned and cleaned[0] == "Unique ID":
                header = cleaned
                break
        if header is None:
            return []

        reader = csv.DictReader(handle, delimiter="\t", fieldnames=header)
        for row in reader:
            uid = _clean(row.get("Unique ID"))
            if not uid:
                continue
            entries.append({
                "unique_id": uid,
                "parent_id": _clean(row.get("Parent")) or None,
                "name": _clean(row.get("Name")) or uid,
                "tier_1": _clean(row.get("Tier 1")) or None,
                "tier_2": _clean(row.get("Tier 2")) or None,
                "tier_3": _clean(row.get("Tier 3")) or None,
                "tier_4": _clean(row.get("Tier 4")) or None,
            })
    return entries


def _upsert_product_rows(conn: sqlite3.Connection, rows: list[dict]) -> None:
    existing = {row["unique_id"] for row in conn.execute("SELECT unique_id FROM iab_product_taxonomy").fetchall()}

    to_insert = []
    to_update = []
    for row in rows:
        if row["unique_id"] in existing:
            to_update.append(row)
        else:
            to_insert.append(row)

    if to_insert:
        conn.executemany(
            """INSERT INTO iab_product_taxonomy
               (unique_id, parent_id, name, tier_1, tier_2, tier_3)
               VALUES (:unique_id, :parent_id, :name, :tier_1, :tier_2, :tier_3)""",
            to_insert,
        )

    if to_update:
        conn.executemany(
            """UPDATE iab_product_taxonomy
               SET parent_id=:parent_id, name=:name,
                   tier_1=:tier_1, tier_2=:tier_2, tier_3=:tier_3,
                   updated_at=datetime('now')
               WHERE unique_id=:unique_id""",
            to_update,
        )


def _upsert_content_rows(conn: sqlite3.Connection, rows: list[dict]) -> None:
    existing = {row["unique_id"] for row in conn.execute("SELECT unique_id FROM iab_content_taxonomy").fetchall()}

    to_insert = []
    to_update = []
    for row in rows:
        if row["unique_id"] in existing:
            to_update.append(row)
        else:
            to_insert.append(row)

    if to_insert:
        conn.executemany(
            """INSERT INTO iab_content_taxonomy
               (unique_id, parent_id, name, tier_1, tier_2, tier_3, tier_4)
               VALUES (:unique_id, :parent_id, :name, :tier_1, :tier_2, :tier_3, :tier_4)""",
            to_insert,
        )

    if to_update:
        conn.executemany(
            """UPDATE iab_content_taxonomy
               SET parent_id=:parent_id, name=:name,
                   tier_1=:tier_1, tier_2=:tier_2, tier_3=:tier_3, tier_4=:tier_4,
                   updated_at=datetime('now')
               WHERE unique_id=:unique_id""",
            to_update,
        )


def _record_version(
    conn: sqlite3.Connection,
    taxonomy_type: str,
    version: str,
    source_file: str,
    entries_count: int,
) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO taxonomy_versions
           (taxonomy_type, version, source_file, entries_count, loaded_at)
           VALUES (?, ?, ?, ?, datetime('now'))""",
        (taxonomy_type, version, source_file, entries_count),
    )
