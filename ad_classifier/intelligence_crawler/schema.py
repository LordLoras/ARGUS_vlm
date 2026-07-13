"""SQLite schema + migrations for ``intelligence_crawler.db`` (own store, WAL mode).

Mirrors the entity-graph schema pattern: a SCHEMA string applied idempotently plus a
migrations table. Reads of submitted/graph data happen elsewhere and are read-only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS intel_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS intel_sources (
  id TEXT PRIMARY KEY,
  brand_name TEXT NOT NULL,
  market TEXT NOT NULL DEFAULT 'US',
  source_type TEXT NOT NULL,
  tier TEXT NOT NULL CHECK (tier IN ('A','B','C')),
  url TEXT,
  platform TEXT,
  platform_id TEXT,
  enabled INTEGER NOT NULL DEFAULT 0,
  poll_interval_hours REAL NOT NULL DEFAULT 12,
  source_activated_at TEXT,
  allowed_domains_json TEXT NOT NULL DEFAULT '[]',
  config_json TEXT NOT NULL DEFAULT '{}',
  notes TEXT,
  archived_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS intel_source_state (
  source_id TEXT PRIMARY KEY REFERENCES intel_sources(id) ON DELETE CASCADE,
  last_attempt_at TEXT,
  last_success_at TEXT,
  next_due_at TEXT,
  last_error TEXT,
  consecutive_errors INTEGER NOT NULL DEFAULT 0,
  etag TEXT,
  last_modified TEXT,
  watermark TEXT,
  lease_until TEXT,
  lease_owner TEXT,
  last_outcome TEXT,
  last_error_category TEXT,
  last_error_code TEXT,
  cooldown_until TEXT,
  diagnostics_json TEXT NOT NULL DEFAULT '[]',
  state_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS intel_crawl_runs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL
    CHECK (status IN ('queued','running','completed','failed','degraded')),
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT,
  source_count INTEGER NOT NULL DEFAULT 0,
  resource_count INTEGER NOT NULL DEFAULT 0,
  signal_count INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_intel_runs_status ON intel_crawl_runs(status, started_at);

CREATE TABLE IF NOT EXISTS intel_resources (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES intel_sources(id) ON DELETE CASCADE,
  run_id TEXT REFERENCES intel_crawl_runs(id) ON DELETE SET NULL,
  resource_type TEXT NOT NULL,
  url TEXT,
  canonical_url TEXT,
  platform TEXT,
  platform_id TEXT,
  content_hash TEXT,
  title TEXT,
  description TEXT,
  published_at TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT,
  fetched_at TEXT NOT NULL,
  is_backfill INTEGER NOT NULL DEFAULT 0,
  variant_count INTEGER,
  has_variants INTEGER NOT NULL DEFAULT 0,
  thumbnail_url TEXT,
  duration_ms INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_intel_resources_source
  ON intel_resources(source_id, published_at);

CREATE TABLE IF NOT EXISTS intel_media_assets (
  id TEXT PRIMARY KEY,
  resource_id TEXT NOT NULL REFERENCES intel_resources(id) ON DELETE CASCADE,
  asset_type TEXT NOT NULL,
  url TEXT,
  thumbnail_url TEXT,
  duration_ms INTEGER,
  content_hash TEXT,
  phash TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS intel_source_runs (
  run_id TEXT NOT NULL REFERENCES intel_crawl_runs(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES intel_sources(id),
  status TEXT NOT NULL CHECK (status IN ('running','polled','partial','skipped','failed')),
  outcome TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  complete INTEGER NOT NULL DEFAULT 1,
  truncated INTEGER NOT NULL DEFAULT 0,
  truncation_reason TEXT,
  new_resources INTEGER NOT NULL DEFAULT 0,
  refreshed INTEGER NOT NULL DEFAULT 0,
  backfilled INTEGER NOT NULL DEFAULT 0,
  filtered INTEGER NOT NULL DEFAULT 0,
  new_signals INTEGER NOT NULL DEFAULT 0,
  error_category TEXT,
  error_code TEXT,
  error TEXT,
  diagnostics_json TEXT NOT NULL DEFAULT '[]',
  request_count INTEGER NOT NULL DEFAULT 0,
  page_count INTEGER NOT NULL DEFAULT 0,
  provider_item_count INTEGER,
  next_due_at TEXT,
  scan_mode TEXT,
  resumed INTEGER NOT NULL DEFAULT 0,
  checkpoint_page INTEGER,
  stop_reason TEXT,
  PRIMARY KEY (run_id, source_id)
);

CREATE INDEX IF NOT EXISTS idx_intel_source_runs_source
  ON intel_source_runs(source_id, started_at DESC);

CREATE TABLE IF NOT EXISTS intel_resource_observations (
  id TEXT PRIMARY KEY,
  resource_id TEXT NOT NULL REFERENCES intel_resources(id),
  source_id TEXT NOT NULL REFERENCES intel_sources(id),
  run_id TEXT NOT NULL REFERENCES intel_crawl_runs(id),
  observed_at TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  resource_json TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(run_id, resource_id)
);

CREATE INDEX IF NOT EXISTS idx_intel_observations_resource
  ON intel_resource_observations(resource_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_intel_observations_source
  ON intel_resource_observations(source_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS intel_campaign_groups (
  id TEXT PRIMARY KEY,
  brand_name TEXT NOT NULL,
  group_key TEXT NOT NULL,
  title TEXT,
  first_seen_at TEXT NOT NULL,
  last_activity_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'candidate',
  UNIQUE(brand_name, group_key)
);

CREATE TABLE IF NOT EXISTS intel_signals (
  id TEXT PRIMARY KEY,
  brand_name TEXT NOT NULL,
  campaign_group_id TEXT REFERENCES intel_campaign_groups(id) ON DELETE SET NULL,
  signal_type TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  title TEXT NOT NULL,
  summary TEXT,
  campaign_name TEXT,
  products_json TEXT NOT NULL DEFAULT '[]',
  first_seen_at TEXT NOT NULL,
  source_published_at TEXT,
  last_seen_at TEXT NOT NULL,
  score_breakdown_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_intel_signals_brand
  ON intel_signals(brand_name, status, source_published_at);

CREATE TABLE IF NOT EXISTS intel_signal_evidence (
  id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL REFERENCES intel_signals(id) ON DELETE CASCADE,
  resource_id TEXT REFERENCES intel_resources(id) ON DELETE SET NULL,
  source_id TEXT REFERENCES intel_sources(id) ON DELETE SET NULL,
  evidence_type TEXT NOT NULL,
  url TEXT,
  text TEXT,
  published_at TEXT,
  confidence REAL,
  UNIQUE(signal_id, id)
);

CREATE TABLE IF NOT EXISTS intel_signal_matches (
  id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL REFERENCES intel_signals(id) ON DELETE CASCADE,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  match_score REAL NOT NULL,
  reasons_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(signal_id, target_type, target_id)
);

CREATE TABLE IF NOT EXISTS intel_review_events (
  id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL REFERENCES intel_signals(id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  note TEXT,
  actor TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def initialize_intelligence_crawler_db(path: Path) -> list[str]:
    """Create the schema if needed. Returns the list of migrations applied this call."""
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
            conn.execute("INSERT OR IGNORE INTO intel_migrations (version) VALUES ('001_initial')")
            migrations.append("001_initial")
        # 002: creative-version projection columns on intel_resources. The CREATE TABLE above
        # already includes them for fresh DBs; ALTER backfills DBs created before 001 had them.
        if "002_resource_variants" not in applied:
            for column, ddl in (
                ("variant_count", "INTEGER"),
                ("has_variants", "INTEGER NOT NULL DEFAULT 0"),
            ):
                if not _column_exists(conn, "intel_resources", column):
                    conn.execute(f"ALTER TABLE intel_resources ADD COLUMN {column} {ddl}")
            conn.execute(
                "INSERT OR IGNORE INTO intel_migrations (version) VALUES ('002_resource_variants')"
            )
            migrations.append("002_resource_variants")
        if "003_crawl_observability" not in applied:
            columns = {
                "intel_sources": (("archived_at", "TEXT"),),
                "intel_source_state": (
                    ("last_outcome", "TEXT"),
                    ("last_error_category", "TEXT"),
                    ("last_error_code", "TEXT"),
                    ("cooldown_until", "TEXT"),
                    ("diagnostics_json", "TEXT NOT NULL DEFAULT '[]'"),
                ),
                "intel_resources": (
                    ("last_seen_at", "TEXT"),
                    ("thumbnail_url", "TEXT"),
                    ("duration_ms", "INTEGER"),
                ),
            }
            for table, additions in columns.items():
                for column, ddl in additions:
                    if not _column_exists(conn, table, column):
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
            # The main schema creates the new ledger tables on both fresh and existing DBs.
            conn.execute(
                "INSERT OR IGNORE INTO intel_migrations (version) "
                "VALUES ('003_crawl_observability')"
            )
            migrations.append("003_crawl_observability")
        if "004_crawl_resume" not in applied:
            source_run_additions = (
                ("scan_mode", "TEXT"),
                ("resumed", "INTEGER NOT NULL DEFAULT 0"),
                ("checkpoint_page", "INTEGER"),
                ("stop_reason", "TEXT"),
            )
            for column, ddl in source_run_additions:
                if not _column_exists(conn, "intel_source_runs", column):
                    conn.execute(f"ALTER TABLE intel_source_runs ADD COLUMN {column} {ddl}")
            if not _column_exists(conn, "intel_source_state", "state_json"):
                conn.execute(
                    "ALTER TABLE intel_source_state "
                    "ADD COLUMN state_json TEXT NOT NULL DEFAULT '{}'"
                )
            conn.execute(
                "INSERT OR IGNORE INTO intel_migrations (version) VALUES ('004_crawl_resume')"
            )
            migrations.append("004_crawl_resume")
        conn.commit()
        return migrations
    finally:
        conn.close()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row["name"]) == column for row in rows)


def _applied_migrations(conn: sqlite3.Connection) -> set[str]:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='intel_migrations'"
    ).fetchone()
    if row is None:
        return set()
    rows = conn.execute("SELECT version FROM intel_migrations").fetchall()
    return {str(item["version"]) for item in rows}
