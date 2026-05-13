from __future__ import annotations

from pathlib import Path

import pytest

from ad_classifier.config import AppConfig
from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.embeddings.image.mock import MockImageEmbedder
from ad_classifier.embeddings.text.mock import MockTextEmbedder
from ad_classifier.ingest.models import IngestArtifacts, IngestFrame, WhisperTranscript
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.preprocess.models import FrameAnalysis
from ad_classifier.vectors.sqlite_vec import SqliteVecStore
from ad_classifier.worker.stages import _write_embeddings


def test_write_embeddings_loads_sqlite_vec_on_fresh_connection(tmp_path: Path):
    db_path = tmp_path / "vectors.db"
    conn = open_database(db_path)
    apply_migrations(conn)
    conn.execute(
        "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, ?)",
        ("ad_vec", str(tmp_path / "ad.mp4"), "2026-01-01T00:00:00"),
    )

    config = AppConfig()
    config.vector_store.text_dim = 8
    config.vector_store.visual_dim = 8

    frame_path = tmp_path / "frame.png"
    frame_path.write_bytes(b"not used by mock image embedder")
    ingest = IngestArtifacts(
        ad_id="ad_vec",
        source_path=tmp_path / "ad.mp4",
        frames_dir=tmp_path,
        frames=[IngestFrame(frame_index=0, time_ms=0, path=frame_path)],
        audio_path=None,
        whisper_path=tmp_path / "whisper.json",
        manifest_path=tmp_path / "manifest.json",
        transcript=WhisperTranscript(text="hello world"),
    )

    text_vector, visual_vector = _write_embeddings(
        conn,
        config,
        "ad_vec",
        ingest,
        [OCRItem(frame_index=0, time_ms=0, text="sale", confidence=1.0, engine="mock")],
        [FrameAnalysis(frame_index=0, time_ms=0, path=frame_path)],
        MockTextEmbedder(dim=8),
        MockImageEmbedder(dim=8),
    )
    conn.commit()

    store = SqliteVecStore(conn, text_dim=8, visual_dim=8)
    assert store.get_text("ad_vec") == pytest.approx(text_vector)
    assert store.get_visual("ad_vec") == pytest.approx(visual_vector)
    frame_hits = store.search_frame_visual(visual_vector, k=5)
    assert frame_hits[0]["ad_id"] == "ad_vec"
    assert frame_hits[0]["frame_index"] == 0
    conn.close()
