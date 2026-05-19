"""Knowledge DB schema — separate SQLite database for taxonomy and rules."""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS iab_product_taxonomy (
    unique_id    TEXT PRIMARY KEY,
    parent_id    TEXT,
    name         TEXT NOT NULL,
    tier_1       TEXT,
    tier_2       TEXT,
    tier_3       TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_iab_product_parent
    ON iab_product_taxonomy(parent_id);
CREATE INDEX IF NOT EXISTS idx_iab_product_tier1
    ON iab_product_taxonomy(tier_1);
CREATE INDEX IF NOT EXISTS idx_iab_product_active
    ON iab_product_taxonomy(active);

CREATE TABLE IF NOT EXISTS iab_content_taxonomy (
    unique_id    TEXT PRIMARY KEY,
    parent_id    TEXT,
    name         TEXT NOT NULL,
    tier_1       TEXT,
    tier_2       TEXT,
    tier_3       TEXT,
    tier_4       TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_iab_content_parent
    ON iab_content_taxonomy(parent_id);
CREATE INDEX IF NOT EXISTS idx_iab_content_tier1
    ON iab_content_taxonomy(tier_1);
CREATE INDEX IF NOT EXISTS idx_iab_content_active
    ON iab_content_taxonomy(active);

CREATE TABLE IF NOT EXISTS brand_category_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_name      TEXT    NOT NULL COLLATE NOCASE,
    primary_category TEXT,
    iab_product_id  TEXT,
    iab_content_ids TEXT,
    subcategory     TEXT,
    source          TEXT    NOT NULL DEFAULT 'manual'
        CHECK (source IN ('manual', 'correction', 'statistical', 'backfill')),
    confidence      REAL    NOT NULL DEFAULT 1.0,
    priority        INTEGER NOT NULL DEFAULT 0,
    active          INTEGER NOT NULL DEFAULT 1,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(brand_name, source)
);

CREATE INDEX IF NOT EXISTS idx_brand_rules_brand
    ON brand_category_rules(brand_name);
CREATE INDEX IF NOT EXISTS idx_brand_rules_active
    ON brand_category_rules(active);

CREATE TABLE IF NOT EXISTS taxonomy_overrides (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    override_type   TEXT NOT NULL
        CHECK (override_type IN ('brand', 'keyword', 'subcategory', 'product_text')),
    pattern         TEXT NOT NULL,
    primary_category TEXT,
    iab_product_id  TEXT,
    iab_content_ids TEXT,
    priority        INTEGER NOT NULL DEFAULT 0,
    active          INTEGER NOT NULL DEFAULT 1,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(override_type, pattern)
);

CREATE INDEX IF NOT EXISTS idx_overrides_type
    ON taxonomy_overrides(override_type);
CREATE INDEX IF NOT EXISTS idx_overrides_active
    ON taxonomy_overrides(active);

CREATE TABLE IF NOT EXISTS correction_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id        TEXT NOT NULL,
    field        TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    source       TEXT NOT NULL DEFAULT 'manual'
        CHECK (source IN ('manual', 'backfill')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_correction_ad
    ON correction_log(ad_id);
CREATE INDEX IF NOT EXISTS idx_correction_field
    ON correction_log(field);

CREATE TABLE IF NOT EXISTS inference_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    taxonomy_type   TEXT NOT NULL
        CHECK (taxonomy_type IN ('product', 'content')),
    target_id       TEXT NOT NULL,
    terms           TEXT NOT NULL,
    context_terms   TEXT NOT NULL DEFAULT '',
    priority        INTEGER NOT NULL DEFAULT 0,
    active          INTEGER NOT NULL DEFAULT 1,
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_inference_target
    ON inference_rules(target_id);
CREATE INDEX IF NOT EXISTS idx_inference_active
    ON inference_rules(active);

CREATE TABLE IF NOT EXISTS taxonomy_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    taxonomy_type TEXT NOT NULL
        CHECK (taxonomy_type IN ('product', 'content')),
    version       TEXT NOT NULL,
    source_file   TEXT,
    entries_count INTEGER,
    loaded_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(taxonomy_type, version)
);

CREATE TABLE IF NOT EXISTS knowledge_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO knowledge_migrations (version) VALUES ('001_initial');
"""

MIGRATIONS = {
    "001_initial": _SCHEMA,
}


def initialize_knowledge_db(path: Path) -> list[str]:
    """Create knowledge DB and apply all pending migrations.

    Returns list of newly applied migration versions.
    """
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        applied = _applied_migrations(conn)
        newly: list[str] = []
        for version, sql in sorted(MIGRATIONS.items()):
            if version in applied:
                continue
            conn.executescript(sql)
            newly.append(version)
        conn.commit()
        return newly
    finally:
        conn.close()


def _applied_migrations(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_migrations'"
    ).fetchall()
    if not rows:
        return set()
    return {
        str(row["version"])
        for row in conn.execute("SELECT version FROM knowledge_migrations").fetchall()
    }
