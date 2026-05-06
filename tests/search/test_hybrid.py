from __future__ import annotations

from pathlib import Path

import pytest

from ad_classifier.db.connection import apply_migrations, load_sqlite_vec, open_database
from ad_classifier.embeddings.text.mock import MockTextEmbedder
from ad_classifier.search.fts import fts_update
from ad_classifier.search.hybrid import hybrid_search
from ad_classifier.vectors.sqlite_vec import SqliteVecStore


@pytest.fixture()
def setup(tmp_path):
    db = tmp_path / "test.db"
    conn = open_database(db)
    apply_migrations(conn)
    try:
        load_sqlite_vec(conn)
    except Exception:
        pytest.skip("sqlite-vec not available")

    # Seed parent ad rows
    for i in range(4):
        conn.execute(
            "INSERT INTO ads (id, source_path, ingested_at) VALUES (?, ?, ?)",
            (f"ad_{i}", f"/tmp/{i}.mp4", "2026-01-01T00:00:00"),
        )

    store = SqliteVecStore(conn, text_dim=8, visual_dim=8)
    store.ensure_tables()

    emb = MockTextEmbedder(dim=8)
    categories = ["retail_ecommerce", "gambling", "health_wellness", "food_beverage"]
    for i in range(4):
        vec = emb.embed(f"ad_{i}")
        store.upsert_text(f"ad_{i}", vec)
        fts_update(
            conn,
            f"ad_{i}",
            brand=f"Brand{i}",
            primary_category=categories[i],
            ocr_text=f"some text for ad {i}",
        )
    conn.commit()
    return conn, store, emb


def test_vector_only_returns_results(setup):
    conn, store, emb = setup
    query_vec = emb.embed("ad_0")
    results = hybrid_search(conn, store, query_vector=query_vec, modality="text", k_final=3)
    assert len(results) >= 1
    assert results[0].ad_id == "ad_0"


def test_text_only_returns_results(setup):
    conn, store, _ = setup
    results = hybrid_search(conn, store, query_text="Brand0", k_final=5)
    assert len(results) >= 1
    assert any(r.ad_id == "ad_0" for r in results)


def test_both_query_types_combined(setup):
    conn, store, emb = setup
    query_vec = emb.embed("ad_1")
    results = hybrid_search(conn, store, query_text="Brand1", query_vector=query_vec, k_final=4)
    assert len(results) >= 1


def test_raises_if_no_query(setup):
    conn, store, _ = setup
    with pytest.raises(ValueError):
        hybrid_search(conn, store)


def test_rrf_score_present(setup):
    conn, store, emb = setup
    results = hybrid_search(conn, store, query_vector=emb.embed("ad_2"), k_final=3)
    assert all(r.rrf_score > 0 for r in results)
