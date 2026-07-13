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

    # Second call applies nothing new.
    assert initialize_intelligence_crawler_db(db) == []

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {row[0] for row in rows}
        source_run_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(intel_source_runs)").fetchall()
        }
    finally:
        conn.close()
    assert names >= EXPECTED_TABLES
    assert {"scan_mode", "resumed", "checkpoint_page", "stop_reason"} <= source_run_columns
