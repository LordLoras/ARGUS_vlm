from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ad_classifier.creative.storyboard import build_storyboard
from ad_classifier.db.connection import initialize_database, open_database


def _conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "storyboard.db"
    initialize_database(db_path)
    return open_database(db_path)


def test_storyboard_segments_shots_and_writes_artifacts(tmp_path: Path):
    conn = _conn(tmp_path)
    try:
        conn.execute(
            """
            INSERT INTO ads (id, source_path, ingested_at, duration_ms, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("ad_story", "/tmp/ad.mp4", datetime.now(UTC).isoformat(), 3500, "completed"),
        )
        frames = [
            (0, 0, "0000000000000000"),
            (1, 500, "0000000000000001"),
            (2, 1500, "ffffffffffffffff"),
            (3, 2000, "fffffffffffffffe"),
        ]
        for frame_index, time_ms, phash in frames:
            conn.execute(
                """
                INSERT INTO frames (ad_id, frame_index, time_ms, path, kept, phash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "ad_story",
                    frame_index,
                    time_ms,
                    str(tmp_path / f"frame_{frame_index}.jpg"),
                    1,
                    phash,
                ),
            )
        frame_zero = conn.execute(
            "SELECT id FROM frames WHERE ad_id = ? AND frame_index = 0",
            ("ad_story",),
        ).fetchone()["id"]
        frame_two = conn.execute(
            "SELECT id FROM frames WHERE ad_id = ? AND frame_index = 2",
            ("ad_story",),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO ocr_items (frame_id, engine, text, confidence)
            VALUES (?, ?, ?, ?)
            """,
            (frame_zero, "paddleocr", "Meet Terra", 0.93),
        )
        conn.execute(
            """
            INSERT INTO ocr_items (frame_id, engine, text, confidence)
            VALUES (?, ?, ?, ?)
            """,
            (frame_two, "paddleocr", "Save today", 0.91),
        )
        conn.execute(
            """
            INSERT INTO transcript_segments (ad_id, start_ms, end_ms, text, confidence)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("ad_story", 1500, 2600, "Save today on the new plan", 0.96),
        )
        conn.commit()

        storyboard = build_storyboard(conn, "ad_story", tmp_path / "out")

        assert storyboard.shot_count == 2
        assert storyboard.shots[0].on_screen_text == ["Meet Terra"]
        assert storyboard.shots[0].transition == "start"
        assert storyboard.shots[1].transition == "cut"
        assert storyboard.shots[1].shot_type == "end_card_or_cta"
        assert storyboard.shots[1].voiceover == "Save today on the new plan"
        assert Path(storyboard.json_path).exists()
        assert Path(storyboard.html_path).exists()
    finally:
        conn.close()
