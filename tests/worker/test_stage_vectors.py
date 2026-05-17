from __future__ import annotations

from pathlib import Path

import pytest

from ad_classifier.config import AppConfig
from ad_classifier.db.connection import apply_migrations, open_database
from ad_classifier.embeddings.image.mock import MockImageEmbedder
from ad_classifier.embeddings.text.mock import MockTextEmbedder
from ad_classifier.ingest.models import IngestArtifacts, IngestFrame, WhisperTranscript
from ad_classifier.pipeline.ocr.models import OCRItem
from ad_classifier.pipeline.paddlevl.models import PaddleVLOutput
from ad_classifier.pipeline.preprocess.models import FrameAnalysis
from ad_classifier.vectors.sqlite_vec import SqliteVecStore
from ad_classifier.worker.document_ocr import (
    document_outputs_to_ocr_items,
    search_ocr_items,
    select_glm_ocr_frames,
)
from ad_classifier.worker.stages import (
    _corrected_ocr_items,
    _write_embeddings,
)


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


def test_select_glm_ocr_frames_prioritizes_gating_then_text_density(tmp_path: Path):
    config = AppConfig()
    config.glm_ocr.enabled = True
    config.glm_ocr.max_frames_per_ad = 2
    config.glm_ocr.min_ocr_chars = 100

    frames = [
        FrameAnalysis(frame_index=0, time_ms=0, path=tmp_path / "0.png"),
        FrameAnalysis(frame_index=1, time_ms=500, path=tmp_path / "1.png"),
        FrameAnalysis(frame_index=2, time_ms=1000, path=tmp_path / "2.png"),
    ]
    ocr_by_frame = {
        0: [OCRItem(frame_index=0, time_ms=0, text="short", confidence=0.2, engine="mock")],
        1: [OCRItem(frame_index=1, time_ms=500, text="A" * 180, confidence=0.95, engine="mock")],
        2: [OCRItem(frame_index=2, time_ms=1000, text="B" * 220, confidence=0.95, engine="mock")],
    }

    selected = select_glm_ocr_frames(
        config=config,
        kept_frames=frames,
        ocr_by_frame=ocr_by_frame,
    )

    assert [frame.frame_index for frame in selected] == [0, 2]


def test_select_glm_ocr_frames_can_run_when_paddle_ocr_disabled(tmp_path: Path):
    config = AppConfig()
    config.ocr.enabled = False
    config.glm_ocr.enabled = True
    config.glm_ocr.max_frames_per_ad = 2

    frames = [
        FrameAnalysis(frame_index=0, time_ms=0, path=tmp_path / "0.png"),
        FrameAnalysis(frame_index=1, time_ms=500, path=tmp_path / "1.png"),
        FrameAnalysis(frame_index=2, time_ms=1000, path=tmp_path / "2.png"),
    ]

    selected = select_glm_ocr_frames(
        config=config,
        kept_frames=frames,
        ocr_by_frame={},
    )

    assert [frame.frame_index for frame in selected] == [0, 1]


def test_document_outputs_become_separate_searchable_ocr_items():
    output = PaddleVLOutput(
        frame_index=4,
        time_ms=2000,
        raw_text="SALE",
        parsed={"text": "SALE\nCall now"},
        parse_ok=True,
        engine="glm_ocr",
    )

    items = document_outputs_to_ocr_items({4: output})

    assert len(items) == 1
    assert items[0].engine == "glm_ocr"
    assert items[0].bbox is None
    assert items[0].confidence is None
    assert items[0].text == "SALE\nCall now"


def test_search_ocr_items_respects_glm_include_switch():
    config = AppConfig()
    config.glm_ocr.enabled = True
    raw = [OCRItem(frame_index=0, time_ms=0, text="paddle", confidence=1.0, engine="paddleocr")]
    glm = [OCRItem(frame_index=0, time_ms=0, text="glm", confidence=None, engine="glm_ocr")]

    assert [item.engine for item in search_ocr_items(raw, glm, config)] == [
        "paddleocr",
        "glm_ocr",
    ]

    config.glm_ocr.include_in_search = False
    assert [item.engine for item in search_ocr_items(raw, glm, config)] == ["paddleocr"]


def test_corrected_ocr_items_keeps_only_cleanup_outputs():
    items = [
        OCRItem(frame_index=0, time_ms=0, text="raw", confidence=1.0, engine="paddleocr"),
        OCRItem(frame_index=0, time_ms=0, text="clean", confidence=0.9, engine="ocr_cleanup"),
        OCRItem(frame_index=1, time_ms=500, text="glm", confidence=None, engine="glm_ocr"),
    ]

    corrected = _corrected_ocr_items(items)

    assert [item.text for item in corrected] == ["clean"]
