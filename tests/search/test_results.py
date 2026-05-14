from __future__ import annotations

from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.search.results import filter_by_min_score_any, filter_by_query_intent
from ad_classifier.vectors.sqlite_vec import SqliteVecStore


class _FakeVectorStore:
    def __init__(self) -> None:
        self.visual = {"ad_car": [0.0, 1.0], "ad_other": [0.2, 0.2]}
        self.frames = {
            SqliteVecStore.frame_key("ad_car", 1): [0.0, 1.0],
            SqliteVecStore.frame_key("ad_other", 1): [0.2, 0.2],
        }

    def get_visual(self, ad_id: str):
        return self.visual.get(ad_id)

    def get_text(self, ad_id: str):
        return self.visual.get(ad_id)

    def get_frame_vectors_batch(self, frame_keys: list[str]):
        return {key: self.frames[key] for key in frame_keys if key in self.frames}


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


def test_filter_by_min_score_any_uses_best_visual_query_vector():
    hits = [
        {"ad_id": "ad_car", "matched_frames": [{"frame_index": 1}]},
        {"ad_id": "ad_other", "matched_frames": [{"frame_index": 1}]},
    ]

    filtered = filter_by_min_score_any(
        _FakeVectorStore(),
        hits,
        [[1.0, 0.0], [0.0, 1.0]],
        min_score=0.9,
        modality="visual",
    )

    assert filtered == [{"ad_id": "ad_car", "matched_frames": [{"frame_index": 1}], "score": 1.0}]
