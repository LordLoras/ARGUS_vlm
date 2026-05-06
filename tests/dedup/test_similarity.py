from __future__ import annotations

from pathlib import Path

import pytest

from ad_classifier.db.connection import apply_migrations, load_sqlite_vec, open_database
from ad_classifier.dedup.similarity import (
    cosine_similarity,
    enrich_related_ads,
    find_similar_by_text,
)
from ad_classifier.embeddings.text.mock import MockTextEmbedder
from ad_classifier.vectors.sqlite_vec import SqliteVecStore


def test_cosine_similarity_identical():
    v = [1.0, 0.0, 0.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(cosine_similarity(a, b)) < 1e-9


def test_cosine_similarity_opposite():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-9


@pytest.fixture()
def store_with_ads(tmp_path):
    db = tmp_path / "test.db"
    conn = open_database(db)
    apply_migrations(conn)
    try:
        load_sqlite_vec(conn)
    except Exception:
        pytest.skip("sqlite-vec not available")
    store = SqliteVecStore(conn, text_dim=8, visual_dim=8)
    store.ensure_tables()

    emb = MockTextEmbedder(dim=8)
    for i in range(5):
        store.upsert_text(f"ad_{i}", emb.embed(f"ad_{i}"))
    conn.commit()
    return store, emb


def test_find_similar_excludes_self(store_with_ads):
    store, emb = store_with_ads
    vec = emb.embed("ad_0")
    results = find_similar_by_text(store, "ad_0", vec, k=5, min_score=0.0)
    assert all(r[0] != "ad_0" for r in results)


def test_find_similar_returns_at_most_k(store_with_ads):
    store, emb = store_with_ads
    vec = emb.embed("ad_0")
    results = find_similar_by_text(store, "ad_0", vec, k=2, min_score=0.0)
    assert len(results) <= 2


def test_enrich_related_ads_returns_related(store_with_ads):
    store, emb = store_with_ads
    vec = emb.embed("ad_0")
    related = enrich_related_ads(store, "ad_0", text_vector=vec, k=3, min_score=0.0)
    assert len(related.semantically_similar) <= 3
    assert all(r.ad_id != "ad_0" for r in related.semantically_similar)


def test_enrich_related_ads_sorted_by_score(store_with_ads):
    store, emb = store_with_ads
    vec = emb.embed("ad_0")
    related = enrich_related_ads(store, "ad_0", text_vector=vec, k=4, min_score=0.0)
    scores = [r.overall_score for r in related.semantically_similar]
    assert scores == sorted(scores, reverse=True)
