from __future__ import annotations

from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.search.results import filter_by_query_intent


def test_filter_by_query_intent_keeps_automotive_for_suv_query(tmp_path):
    conn = open_database(tmp_path / "intent.db")
    apply_migrations(conn)
    rows = [
        ("ad_jeep", "Jeep", "automotive"),
        ("ad_hvac", "Prillaman", "home_improvement"),
    ]
    for ad_id, brand, category in rows:
        conn.execute(
            """
            INSERT INTO ads (id, source_path, ingested_at, brand_name, primary_category)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ad_id, f"/tmp/{ad_id}.mp4", "2026-01-01T00:00:00", brand, category),
        )

    hits = [{"ad_id": "ad_hvac"}, {"ad_id": "ad_jeep"}]

    assert filter_by_query_intent(conn, hits, "luxury suv") == [{"ad_id": "ad_jeep"}]


def test_filter_by_query_intent_leaves_uncategorized_query_alone(tmp_path):
    conn = open_database(tmp_path / "intent.db")
    apply_migrations(conn)
    conn.execute(
        """
        INSERT INTO ads (id, source_path, ingested_at, brand_name, primary_category)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("ad_any", "/tmp/any.mp4", "2026-01-01T00:00:00", "Any", "other"),
    )

    hits = [{"ad_id": "ad_any"}]

    assert filter_by_query_intent(conn, hits, "purple elephant") == hits
