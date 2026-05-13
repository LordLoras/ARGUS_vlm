from __future__ import annotations

from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.search.fts import fts_search_expanded, fts_update


def test_fts_search_expanded_matches_prefix_terms(tmp_path):
    conn = open_database(tmp_path / "fts.db")
    apply_migrations(conn)
    conn.execute(
        "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, ?)",
        ("ad_gov", "/tmp/gov.mp4", "2026-01-01T00:00:00"),
    )
    fts_update(
        conn,
        "ad_gov",
        brand="Becerra For Governor",
        primary_category="political",
        ocr_text="California gubernatorial race",
    )

    results = fts_search_expanded(conn, "gov", limit=10)

    assert [ad_id for ad_id, _score in results] == ["ad_gov"]


def test_fts_search_expanded_matches_multi_token_prefixes(tmp_path):
    conn = open_database(tmp_path / "fts.db")
    apply_migrations(conn)
    conn.execute(
        "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, ?)",
        ("ad_car", "/tmp/car.mp4", "2026-01-01T00:00:00"),
    )
    fts_update(
        conn,
        "ad_car",
        brand="Example Auto",
        primary_category="automotive",
        ocr_text="A red car driving through downtown",
    )

    results = fts_search_expanded(conn, "red ca", limit=10)

    assert [ad_id for ad_id, _score in results] == ["ad_car"]


def test_fts_search_expanded_does_not_match_car_inside_healthcare(tmp_path):
    conn = open_database(tmp_path / "fts.db")
    apply_migrations(conn)
    conn.execute(
        "INSERT INTO ads (id, source_path, ingested_at, primary_category) VALUES (?, ?, ?, ?)",
        ("ad_dose", "/tmp/dose.mp4", "2026-01-01T00:00:00", "healthcare_pharma"),
    )
    conn.execute(
        "INSERT INTO ads (id, source_path, ingested_at, primary_category) VALUES (?, ?, ?, ?)",
        ("ad_jeep", "/tmp/jeep.mp4", "2026-01-01T00:00:00", "automotive"),
    )
    fts_update(conn, "ad_dose", brand="Dose", primary_category="healthcare_pharma")
    fts_update(conn, "ad_jeep", brand="Jeep", primary_category="automotive")

    results = fts_search_expanded(conn, "car", limit=10)

    assert [ad_id for ad_id, _score in results] == ["ad_jeep"]
