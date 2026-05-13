from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ad_classifier.db.connection import apply_migrations, load_sqlite_vec, open_database
from ad_classifier.embeddings.text.mock import MockTextEmbedder
from ad_classifier.embeddings.image.mock import MockImageEmbedder
from ad_classifier.vectors.sqlite_vec import SqliteVecStore
from ad_classifier.vectors.store import deserialize_float32, serialize_float32


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store(tmp_path: Path, text_dim=8, visual_dim=8) -> tuple[sqlite3.Connection, SqliteVecStore]:
    db = tmp_path / "test.db"
    conn = open_database(db)
    apply_migrations(conn)
    try:
        load_sqlite_vec(conn)
    except Exception:
        pytest.skip("sqlite-vec not available in this environment")
    store = SqliteVecStore(conn, text_dim=text_dim, visual_dim=visual_dim)
    store.ensure_tables()
    return conn, store


def _vec(dim: int, seed: int = 1) -> list[float]:
    emb = MockTextEmbedder(dim=dim)
    return emb.embed(f"seed_{seed}")


# ---------------------------------------------------------------------------
# serialize / deserialize roundtrip
# ---------------------------------------------------------------------------


def test_serialize_roundtrip():
    v = [0.1, 0.2, -0.3, 0.99]
    blob = serialize_float32(v)
    back = deserialize_float32(blob)
    assert len(back) == len(v)
    assert all(abs(a - b) < 1e-6 for a, b in zip(v, back))


# ---------------------------------------------------------------------------
# Text embeddings
# ---------------------------------------------------------------------------


def test_upsert_and_get_text(tmp_path):
    conn, store = _store(tmp_path)
    vec = _vec(8, seed=1)
    store.upsert_text("ad_1", vec)
    conn.commit()
    result = store.get_text("ad_1")
    assert result is not None
    assert len(result) == 8
    assert all(abs(a - b) < 1e-5 for a, b in zip(vec, result))


def test_upsert_overwrites_text(tmp_path):
    conn, store = _store(tmp_path)
    store.upsert_text("ad_1", _vec(8, seed=1))
    conn.commit()
    new_vec = _vec(8, seed=2)
    store.upsert_text("ad_1", new_vec)
    conn.commit()
    result = store.get_text("ad_1")
    assert all(abs(a - b) < 1e-5 for a, b in zip(new_vec, result))


def test_get_text_nonexistent_returns_none(tmp_path):
    _, store = _store(tmp_path)
    assert store.get_text("nonexistent") is None


def test_search_text_returns_closest(tmp_path):
    conn, store = _store(tmp_path, text_dim=8)
    vecs = {f"ad_{i}": _vec(8, seed=i) for i in range(5)}
    for ad_id, vec in vecs.items():
        store.upsert_text(ad_id, vec)
    conn.commit()

    query = _vec(8, seed=0)
    results = store.search_text(query, k=3)
    assert len(results) <= 3
    # First result should be ad_0 (exact same vector)
    assert results[0][0] == "ad_0"
    assert results[0][1] < 0.01  # near-zero distance


# ---------------------------------------------------------------------------
# Visual embeddings
# ---------------------------------------------------------------------------


def test_upsert_and_get_visual(tmp_path):
    conn, store = _store(tmp_path, visual_dim=8)
    emb = MockImageEmbedder(dim=8)
    from pathlib import Path
    vec = emb.embed(Path("/img/a.png"))
    store.upsert_visual("ad_v", vec)
    conn.commit()
    result = store.get_visual("ad_v")
    assert result is not None
    assert len(result) == 8


def test_search_visual_returns_results(tmp_path):
    conn, store = _store(tmp_path, visual_dim=8)
    emb = MockImageEmbedder(dim=8)
    from pathlib import Path
    for i in range(4):
        vec = emb.embed(Path(f"/img/{i}.png"))
        store.upsert_visual(f"ad_{i}", vec)
    conn.commit()
    query = emb.embed(Path("/img/0.png"))
    results = store.search_visual(query, k=2)
    assert results[0][0] == "ad_0"


def test_search_frame_visual_returns_frame_metadata(tmp_path):
    conn, store = _store(tmp_path, visual_dim=8)
    conn.execute(
        "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, ?)",
        ("ad_frame", "/tmp/ad.mp4", "2026-01-01T00:00:00"),
    )
    conn.execute(
        """
        INSERT INTO frames (ad_id, frame_index, time_ms, path, kept)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("ad_frame", 3, 1500, "/tmp/frame.png", 1),
    )
    emb = MockImageEmbedder(dim=8)
    vec = emb.embed(Path("/img/frame.png"))
    store.upsert_frame_visual("ad_frame", 3, 1500, vec)
    conn.commit()

    results = store.search_frame_visual(vec, k=5)

    assert results[0]["ad_id"] == "ad_frame"
    assert results[0]["frame_index"] == 3
    assert results[0]["time_ms"] == 1500
    assert results[0]["path"] == "/tmp/frame.png"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_removes_both(tmp_path):
    conn, store = _store(tmp_path)
    store.upsert_text("ad_x", _vec(8))
    store.upsert_visual("ad_x", _vec(8))
    conn.commit()
    store.delete("ad_x")
    conn.commit()
    assert store.get_text("ad_x") is None
    assert store.get_visual("ad_x") is None
