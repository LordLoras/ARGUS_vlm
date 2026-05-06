from __future__ import annotations

from PIL import Image, ImageDraw

from ad_classifier.config import DedupConfig
from ad_classifier.db.connection import initialize_database, open_database
from ad_classifier.db.repositories import AdRepository
from ad_classifier.dedup.file_hash import source_sha256
from ad_classifier.dedup.phash import hamming_distance, image_phash, mean_phash
from ad_classifier.dedup.service import check_frame_phashes
from ad_classifier.models.ads import AdRecord


def test_source_sha256_is_stable(tmp_path):
    path = tmp_path / "ad.mp4"
    path.write_bytes(b"same ad bytes")

    assert source_sha256(path) == source_sha256(path)


def test_mean_phash_and_hamming_distance(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (64, 64), color=(255, 255, 255)).save(first)
    Image.new("RGB", (64, 64), color=(255, 255, 255)).save(second)

    phash = mean_phash([first, second])

    assert phash is not None
    assert hamming_distance(phash, image_phash(first)) == 0


def test_check_frame_phashes_finds_near_duplicate(tmp_path):
    db_path = tmp_path / "ad_classifier.db"
    initialize_database(db_path)
    frame = tmp_path / "frame.png"
    Image.new("RGB", (64, 64), color=(10, 20, 30)).save(frame)
    phash = mean_phash([frame])
    assert phash is not None

    conn = open_database(db_path)
    try:
        AdRepository(conn).create(
            AdRecord(
                id="ad_existing1",
                source_path="existing.mp4",
                status="completed",
                phash_mean=phash,
            )
        )
        conn.commit()

        result = check_frame_phashes(
            conn=conn,
            config=DedupConfig(skip_on_near_duplicate=True, phash_distance_threshold=0),
            frame_paths=[frame],
            exclude_ad_id="ad_new0001",
            source_hash="abc123",
        )
    finally:
        conn.close()

    assert result.phash_mean == phash
    assert result.near_duplicate_of == "ad_existing1"
    assert result.phash_distance == 0
    assert result.skipped is True


def test_check_frame_phashes_respects_threshold(tmp_path):
    db_path = tmp_path / "ad_classifier.db"
    initialize_database(db_path)
    existing_frame = tmp_path / "existing.png"
    new_frame = tmp_path / "new.png"
    Image.new("RGB", (64, 64), color=(0, 0, 0)).save(existing_frame)
    new_image = Image.new("RGB", (64, 64), color=(255, 255, 255))
    draw = ImageDraw.Draw(new_image)
    draw.rectangle((0, 0, 31, 63), fill=(0, 0, 0))
    draw.line((0, 0, 63, 63), fill=(255, 0, 0), width=4)
    new_image.save(new_frame)
    existing_phash = mean_phash([existing_frame])
    assert existing_phash is not None

    conn = open_database(db_path)
    try:
        AdRepository(conn).create(
            AdRecord(
                id="ad_existing1",
                source_path="existing.mp4",
                status="completed",
                phash_mean=existing_phash,
            )
        )
        conn.commit()

        result = check_frame_phashes(
            conn=conn,
            config=DedupConfig(skip_on_near_duplicate=True, phash_distance_threshold=0),
            frame_paths=[new_frame],
            exclude_ad_id="ad_new0001",
        )
    finally:
        conn.close()

    assert result.near_duplicate_of is None
    assert result.skipped is False
