from __future__ import annotations

import sqlite3

import pytest

from ad_classifier.db.connection import (
    initialize_database,
    list_user_tables,
    open_database,
    open_readonly_database,
)
from ad_classifier.db.repositories import AdRepository, JobRepository
from ad_classifier.models.ads import AdRecord
from ad_classifier.models.jobs import JobRecord


def test_initialize_database_creates_schema_and_wal(tmp_path):
    db_path = tmp_path / "ad_classifier.db"

    result = initialize_database(db_path)

    assert result.db_path == db_path.resolve()
    assert result.journal_mode == "wal"
    assert result.sqlite_vec_version is not None
    assert result.migrations_applied == ["001_initial", "002_marketing_tracking"]

    conn = open_database(db_path)
    try:
        tables = set(list_user_tables(conn))
        assert {
            "ads",
            "frames",
            "ocr_items",
            "transcript_segments",
            "rule_triggers",
            "classifications",
            "marketing_entities",
            "jobs",
            "campaigns",
            "ad_campaigns",
            "ads_fts",
            "agent_sessions",
            "agent_messages",
            "schema_migrations",
        }.issubset(tables)
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        ad_columns = {row["name"] for row in conn.execute("PRAGMA table_info(ads)").fetchall()}
        assert {
            "advertiser_name",
            "website_domain",
            "phone_number",
            "landing_page_domain",
        }.issubset(ad_columns)
        marketing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(marketing_entities)").fetchall()
        }
        assert {
            "contact_points_json",
            "advertiser_json",
            "landing_page_json",
            "offer_terms_json",
            "creative_attributes_json",
            "campaign_signals_json",
        }.issubset(marketing_columns)
    finally:
        conn.close()


def test_initialize_database_is_idempotent(tmp_path):
    db_path = tmp_path / "ad_classifier.db"

    initialize_database(db_path)
    second = initialize_database(db_path)

    assert second.migrations_applied == []


def test_readonly_connection_enforces_query_only(tmp_path):
    db_path = tmp_path / "ad_classifier.db"
    initialize_database(db_path)

    conn = open_readonly_database(db_path)
    try:
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute(
                "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                ("ad_12345678", "sample.mp4"),
            )
    finally:
        conn.close()


def test_basic_repositories_round_trip(tmp_path):
    db_path = tmp_path / "ad_classifier.db"
    initialize_database(db_path)

    conn = open_database(db_path)
    try:
        ads = AdRepository(conn)
        jobs = JobRepository(conn)

        ads.create(AdRecord(id="ad_abcd1234", source_path="sample.mp4", status="new"))
        jobs.create(JobRecord(id="job_1", ad_id="ad_abcd1234", state="queued", progress=0.0))
        conn.commit()

        ad = ads.get("ad_abcd1234")
        job = jobs.get("job_1")

        assert ad is not None
        assert ad.source_path == "sample.mp4"
        assert job is not None
        assert job.state == "queued"
    finally:
        conn.close()
