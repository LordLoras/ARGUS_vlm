from __future__ import annotations

import sqlite3

from ad_classifier.intelligence_crawler.schema import initialize_intelligence_crawler_db

EXPECTED_TABLES = {
    "intel_migrations",
    "intel_sources",
    "intel_source_state",
    "intel_source_runs",
    "intel_crawl_runs",
    "intel_resources",
    "intel_resource_observations",
    "intel_resource_changes",
    "intel_service_heartbeats",
    "intel_media_assets",
    "intel_campaign_groups",
    "intel_signals",
    "intel_signal_evidence",
    "intel_signal_matches",
    "intel_review_events",
}


def test_initialize_creates_tables_and_is_idempotent(tmp_path):
    db = tmp_path / "intel.db"
    applied = initialize_intelligence_crawler_db(db)
    assert "001_initial" in applied
    assert "003_crawl_observability" in applied
    assert "004_crawl_resume" in applied
    assert "005_service_runtime" in applied

    # Second call applies nothing new.
    assert initialize_intelligence_crawler_db(db) == []

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {row[0] for row in rows}
        source_run_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(intel_source_runs)").fetchall()
        }
        crawl_run_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(intel_crawl_runs)").fetchall()
        }
    finally:
        conn.close()
    assert names >= EXPECTED_TABLES
    assert {"scan_mode", "resumed", "checkpoint_page", "stop_reason"} <= source_run_columns
    assert {
        "request_json",
        "idempotency_key",
        "lease_owner",
        "lease_until",
        "heartbeat_at",
        "attempt_count",
    } <= crawl_run_columns


def test_migration_upgrades_pre_service_runtime_database(tmp_path):
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE intel_migrations (version TEXT PRIMARY KEY, applied_at TEXT);
        INSERT INTO intel_migrations(version) VALUES
          ('001_initial'), ('002_resource_variants'),
          ('003_crawl_observability'), ('004_crawl_resume');
        CREATE TABLE intel_crawl_runs (
          id TEXT PRIMARY KEY, status TEXT NOT NULL, started_at TEXT,
          finished_at TEXT, source_count INTEGER DEFAULT 0,
          resource_count INTEGER DEFAULT 0, signal_count INTEGER DEFAULT 0,
          error TEXT, summary_json TEXT DEFAULT '{}'
        );
        """)
    conn.commit()
    conn.close()

    assert initialize_intelligence_crawler_db(db) == ["005_service_runtime"]
    conn = sqlite3.connect(db)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(intel_crawl_runs)")}
    finally:
        conn.close()
    assert {"request_json", "idempotency_key", "lease_owner", "attempt_count"} <= columns
