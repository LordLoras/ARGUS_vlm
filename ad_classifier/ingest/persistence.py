from __future__ import annotations

import sqlite3
from pathlib import Path

from ad_classifier.config import AppConfig, resolve_config_path
from ad_classifier.db.connection import initialize_database, open_database
from ad_classifier.db.repositories import AdRepository
from ad_classifier.dedup.models import DedupResult
from ad_classifier.ingest.models import (
    IngestFrame,
    TranscriptSegment,
    VideoMetadata,
    WhisperTranscript,
)
from ad_classifier.models.ads import AdRecord, AdStatus


def persist_ingest(
    *,
    config: AppConfig,
    config_file: Path,
    ad_id: str,
    source_path: Path,
    source_hash: str,
    metadata: VideoMetadata,
    frames: list[IngestFrame],
    transcript: WhisperTranscript,
    dedup: DedupResult,
    status: AdStatus,
) -> None:
    db_path = resolve_config_path(config.paths.sqlite_path, config_file)
    initialize_database(db_path)
    conn = open_database(db_path)
    try:
        AdRepository(conn).upsert_ingest(
            AdRecord(
                id=ad_id,
                source_path=str(source_path),
                duration_ms=metadata.duration_ms,
                width=metadata.width,
                height=metadata.height,
                fps=metadata.fps,
                status=status,
                source_hash=source_hash,
                phash_mean=dedup.phash_mean,
            )
        )
        replace_frame_rows(conn, ad_id, frames)
        replace_transcript_rows(conn, ad_id, transcript.segments)
        conn.commit()
    finally:
        conn.close()


def replace_frame_rows(conn: sqlite3.Connection, ad_id: str, frames: list[IngestFrame]) -> None:
    conn.execute("DELETE FROM frames WHERE ad_id = ?", (ad_id,))
    conn.executemany(
        """
        INSERT INTO frames (ad_id, frame_index, time_ms, path, kept)
        VALUES (?, ?, ?, ?, 1)
        """,
        [(ad_id, frame.frame_index, frame.time_ms, str(frame.path)) for frame in frames],
    )


def replace_transcript_rows(
    conn: sqlite3.Connection,
    ad_id: str,
    segments: list[TranscriptSegment],
) -> None:
    conn.execute("DELETE FROM transcript_segments WHERE ad_id = ?", (ad_id,))
    conn.executemany(
        """
        INSERT INTO transcript_segments (ad_id, start_ms, end_ms, text, confidence)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (ad_id, segment.start_ms, segment.end_ms, segment.text, segment.confidence)
            for segment in segments
        ],
    )
