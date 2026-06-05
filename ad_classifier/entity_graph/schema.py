from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS entity_graph_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entity_sources (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL
    CHECK (source_type IN ('submitted_ad', 'taxonomy', 'discovery_only', 'user', 'resolver')),
  label TEXT NOT NULL,
  url TEXT,
  ad_id TEXT,
  payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entity_nodes (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL
    CHECK (type IN ('product', 'brand', 'company', 'category', 'taxonomy', 'ad')),
  canonical_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL
    CHECK (status IN ('candidate', 'confirmed_unreviewed', 'confirmed_reviewed', 'rejected')),
  confidence REAL NOT NULL DEFAULT 0.0,
  generated_from_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(type, normalized_name)
);

CREATE INDEX IF NOT EXISTS idx_entity_nodes_type_status
  ON entity_nodes(type, status);
CREATE INDEX IF NOT EXISTS idx_entity_nodes_normalized
  ON entity_nodes(normalized_name);

CREATE TABLE IF NOT EXISTS entity_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id TEXT NOT NULL REFERENCES entity_nodes(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  normalized_alias TEXT NOT NULL,
  source_id TEXT REFERENCES entity_sources(id) ON DELETE SET NULL,
  confidence REAL NOT NULL DEFAULT 0.0,
  status TEXT NOT NULL
    CHECK (status IN ('candidate', 'confirmed_unreviewed', 'confirmed_reviewed', 'rejected')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(node_id, normalized_alias, source_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_aliases_node
  ON entity_aliases(node_id);
CREATE INDEX IF NOT EXISTS idx_entity_aliases_normalized
  ON entity_aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS entity_edges (
  id TEXT PRIMARY KEY,
  source_node_id TEXT NOT NULL REFERENCES entity_nodes(id) ON DELETE CASCADE,
  target_node_id TEXT NOT NULL REFERENCES entity_nodes(id) ON DELETE CASCADE,
  relation TEXT NOT NULL
    CHECK (relation IN ('BRANDED_BY', 'OWNED_BY', 'IN_CATEGORY', 'MAPS_TO_TAXONOMY', 'MENTIONED_IN_AD')),
  confidence REAL NOT NULL DEFAULT 0.0,
  status TEXT NOT NULL
    CHECK (status IN ('candidate', 'confirmed_unreviewed', 'confirmed_reviewed', 'rejected')),
  source_id TEXT REFERENCES entity_sources(id) ON DELETE SET NULL,
  evidence_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(source_node_id, target_node_id, relation, source_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_edges_source
  ON entity_edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_entity_edges_target
  ON entity_edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_entity_edges_relation
  ON entity_edges(relation);

CREATE TABLE IF NOT EXISTS entity_observations (
  id TEXT PRIMARY KEY,
  node_id TEXT NOT NULL REFERENCES entity_nodes(id) ON DELETE CASCADE,
  ad_id TEXT NOT NULL,
  field TEXT NOT NULL,
  evidence_text TEXT NOT NULL,
  source TEXT NOT NULL,
  time_ms INTEGER,
  frame_index INTEGER,
  confidence REAL NOT NULL DEFAULT 0.0,
  source_id TEXT REFERENCES entity_sources(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(node_id, ad_id, field, evidence_text, source)
);

CREATE INDEX IF NOT EXISTS idx_entity_observations_node
  ON entity_observations(node_id);
CREATE INDEX IF NOT EXISTS idx_entity_observations_ad
  ON entity_observations(ad_id);

CREATE TABLE IF NOT EXISTS taxonomy_mappings (
  id TEXT PRIMARY KEY,
  entity_id TEXT NOT NULL REFERENCES entity_nodes(id) ON DELETE CASCADE,
  taxonomy_type TEXT NOT NULL CHECK (taxonomy_type IN ('product', 'content', 'category')),
  taxonomy_id TEXT NOT NULL,
  taxonomy_name TEXT,
  relation TEXT NOT NULL DEFAULT 'maps_to',
  confidence REAL NOT NULL DEFAULT 0.0,
  status TEXT NOT NULL
    CHECK (status IN ('candidate', 'confirmed_unreviewed', 'confirmed_reviewed', 'rejected')),
  source_id TEXT REFERENCES entity_sources(id) ON DELETE SET NULL,
  evidence_text TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(entity_id, taxonomy_type, taxonomy_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_taxonomy_mappings_entity
  ON taxonomy_mappings(entity_id);
CREATE INDEX IF NOT EXISTS idx_taxonomy_mappings_taxonomy
  ON taxonomy_mappings(taxonomy_type, taxonomy_id);

CREATE TABLE IF NOT EXISTS resolver_runs (
  id TEXT PRIMARY KEY,
  mode TEXT NOT NULL,
  fully_automatic INTEGER NOT NULL DEFAULT 0,
  source_ad_count INTEGER NOT NULL DEFAULT 0,
  created_count INTEGER NOT NULL DEFAULT 0,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  confirmed_unreviewed_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

MIGRATION_002 = """
CREATE TABLE IF NOT EXISTS ad_change_suggestions (
  id TEXT PRIMARY KEY,
  ad_id TEXT NOT NULL,
  source_id TEXT REFERENCES entity_sources(id) ON DELETE SET NULL,
  field_path TEXT NOT NULL
    CHECK (field_path IN ('ads.brand_name', 'ads.products_text', 'ads.primary_category', 'ads.subcategory')),
  current_value TEXT,
  suggested_value TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.0,
  reason TEXT NOT NULL,
  evidence_text TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected', 'applied')),
  apply_safety TEXT NOT NULL DEFAULT 'review_only'
    CHECK (apply_safety IN ('safe_projection_update', 'review_only', 'do_not_apply')),
  payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  reviewed_at TEXT,
  applied_at TEXT,
  UNIQUE(ad_id, field_path, suggested_value, source_id)
);

CREATE INDEX IF NOT EXISTS idx_ad_change_suggestions_status
  ON ad_change_suggestions(status, ad_id);
CREATE INDEX IF NOT EXISTS idx_ad_change_suggestions_ad
  ON ad_change_suggestions(ad_id);
"""


def initialize_entity_graph_db(path: Path) -> list[str]:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        applied = _applied_migrations(conn)
        migrations: list[str] = []
        conn.executescript(SCHEMA)
        if "001_initial" not in applied:
            conn.execute(
                "INSERT OR IGNORE INTO entity_graph_migrations (version) VALUES ('001_initial')"
            )
            migrations.append("001_initial")
        if "002_ad_change_suggestions" not in applied:
            conn.executescript(MIGRATION_002)
            conn.execute(
                "INSERT OR IGNORE INTO entity_graph_migrations (version) VALUES ('002_ad_change_suggestions')"
            )
            migrations.append("002_ad_change_suggestions")
        conn.commit()
        return migrations
    finally:
        conn.close()


def _applied_migrations(conn: sqlite3.Connection) -> set[str]:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entity_graph_migrations'"
    ).fetchone()
    if row is None:
        return set()
    rows = conn.execute("SELECT version FROM entity_graph_migrations").fetchall()
    return {str(item["version"]) for item in rows}
