from __future__ import annotations

import sqlite3

from ad_classifier.config import PostOCRDedupConfig
from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.db.repositories.ads import AdRepository
from ad_classifier.dedup.post_ocr import find_post_ocr_duplicate
from ad_classifier.models.ads import AdRecord


def test_post_ocr_marks_reencoded_exact_duplicate(tmp_path):
    conn = _db(tmp_path)
    try:
        _insert_ad(
            conn,
            "ad_original",
            phash_mean="0000000000000000",
            frame_phashes=["0000000000000000", "1111111111111111", "2222222222222222"],
            ocr_text=(
                "Jeep Grand Cherokee 0% APR for 60 months "
                "$16.67 per month Sales tax covered"
            ),
            transcript_text="Jeep Grand Cherokee offer with zero percent APR for sixty months.",
        )
        _insert_ad(
            conn,
            "ad_copy",
            status="processing",
            phash_mean="0000000000000001",
            frame_phashes=["0000000000000000", "1111111111111111", "2222222222222222"],
            ocr_text=(
                "Jeep Grand Cherokee 0% APR for 60 months "
                "$16.67 per month sales tax covered"
            ),
            transcript_text="Jeep Grand Cherokee offer with zero percent APR for sixty months.",
        )

        match = find_post_ocr_duplicate(conn, "ad_copy", PostOCRDedupConfig())

        assert match is not None
        assert match.ad_id == "ad_original"
        assert match.verdict == "exact_duplicate"
        assert match.frame_match_ratio == 1.0
    finally:
        conn.close()


def test_post_ocr_preserves_same_campaign_with_changed_offer(tmp_path):
    conn = _db(tmp_path)
    try:
        _insert_ad(
            conn,
            "ad_offer_a",
            phash_mean="0000000000000000",
            frame_phashes=["0000000000000000", "1111111111111111", "2222222222222222"],
            ocr_text=(
                "Jeep Grand Cherokee 0% APR for 60 months "
                "$16.67 per month Sales tax covered"
            ),
            transcript_text="Jeep Grand Cherokee 60 month financing offer.",
        )
        _insert_ad(
            conn,
            "ad_offer_b",
            status="processing",
            phash_mean="0000000000000003",
            frame_phashes=["0000000000000000", "1111111111111111", "2222222222222222"],
            ocr_text=(
                "Jeep Grand Cherokee Wrangler 0% APR for 36 months "
                "$27.78 per month No monthly payments for 90 days"
            ),
            transcript_text="Jeep Grand Cherokee 36 month financing with no payments for 90 days.",
        )

        match = find_post_ocr_duplicate(conn, "ad_offer_b", PostOCRDedupConfig())

        assert match is not None
        assert match.ad_id == "ad_offer_a"
        assert match.verdict == "same_campaign_different_offer"
        assert match.signature_similarity < PostOCRDedupConfig().min_signature_similarity
    finally:
        conn.close()


def test_post_ocr_candidate_pruning_uses_mean_phash(tmp_path):
    conn = _db(tmp_path)
    try:
        _insert_ad(
            conn,
            "ad_far",
            phash_mean="ffffffffffffffff",
            frame_phashes=["ffffffffffffffff", "eeeeeeeeeeeeeeee"],
            ocr_text="Same words same offer $10 off today",
            transcript_text="Same words same offer ten dollars off today.",
        )
        _insert_ad(
            conn,
            "ad_current",
            status="processing",
            phash_mean="0000000000000000",
            frame_phashes=["0000000000000000", "1111111111111111"],
            ocr_text="Same words same offer $10 off today",
            transcript_text="Same words same offer ten dollars off today.",
        )

        match = find_post_ocr_duplicate(conn, "ad_current", PostOCRDedupConfig())

        assert match is None
    finally:
        conn.close()


def _db(tmp_path) -> sqlite3.Connection:
    conn = open_database(tmp_path / "post_ocr.db")
    apply_migrations(conn)
    return conn


def _insert_ad(
    conn: sqlite3.Connection,
    ad_id: str,
    *,
    phash_mean: str,
    frame_phashes: list[str],
    ocr_text: str,
    transcript_text: str,
    status: str = "completed",
) -> None:
    AdRepository(conn).create(
        AdRecord(
            id=ad_id,
            source_path=f"{ad_id}.mp4",
            status=status,
            duration_ms=10_000,
            phash_mean=phash_mean,
        )
    )
    for index, phash in enumerate(frame_phashes):
        cursor = conn.execute(
            """
            INSERT INTO frames (ad_id, frame_index, time_ms, path, kept, phash)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (ad_id, index, index * 500, f"{ad_id}_{index}.png", phash),
        )
        conn.execute(
            """
            INSERT INTO ocr_items (frame_id, engine, text)
            VALUES (?, 'paddleocr', ?)
            """,
            (cursor.lastrowid, ocr_text if index == 0 else "Visit dealer today"),
        )
    conn.execute(
        """
        INSERT INTO transcript_segments (ad_id, start_ms, end_ms, text, confidence)
        VALUES (?, 0, 10000, ?, 0.9)
        """,
        (ad_id, transcript_text),
    )
    conn.commit()
