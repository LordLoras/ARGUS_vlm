from __future__ import annotations

import pytest

from ad_classifier.db.connection import apply_migrations, load_sqlite_vec, open_database
from ad_classifier.db.repositories.ads import AdRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.dedup.similarity import (
    cosine_similarity,
    enrich_related_ads,
    find_similar_by_text,
)
from ad_classifier.embeddings.text.mock import MockTextEmbedder
from ad_classifier.models.ads import AdRecord
from ad_classifier.models.marketing import BrandEntity, MarketingEntities, OfferEntity
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


def test_find_similar_rescores_candidates_with_cosine():
    class FakeStore:
        def search_text(self, query, k):
            return [("ad_scaled", 100.0)]

        def get_text(self, ad_id):
            return [10.0, 0.0] if ad_id == "ad_scaled" else None

    results = find_similar_by_text(FakeStore(), "ad_query", [1.0, 0.0], min_score=0.95)

    assert results == [("ad_scaled", 1.0)]


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


def test_enrich_related_ads_marks_same_campaign_variant(tmp_path):
    db = tmp_path / "related.db"
    conn = open_database(db)
    apply_migrations(conn)
    try:
        load_sqlite_vec(conn)
    except Exception:
        pytest.skip("sqlite-vec not available")

    ads = AdRepository(conn)
    marketing = MarketingEntityRepository(conn)
    store = SqliteVecStore(conn, text_dim=3, visual_dim=3)
    store.ensure_tables()

    ads.create(AdRecord(id="ad_a", source_path="a.mp4", status="completed"))
    ads.create(AdRecord(id="ad_b", source_path="b.mp4", status="completed"))
    marketing.upsert(
        "ad_a",
        MarketingEntities(
            brand=BrandEntity(name="Jeep"),
            products=["Wrangler"],
            offers=[OfferEntity(text="$400/mo lease")],
        ),
    )
    marketing.upsert(
        "ad_b",
        MarketingEntities(
            brand=BrandEntity(name="Jeep"),
            products=["Grand Cherokee"],
            offers=[OfferEntity(text="$4,500 bonus cash")],
        ),
    )
    store.upsert_text("ad_a", [1.0, 0.0, 0.0])
    store.upsert_text("ad_b", [0.8, 0.6, 0.0])
    store.upsert_visual("ad_a", [1.0, 0.0, 0.0])
    store.upsert_visual("ad_b", [1.0, 0.0, 0.0])
    conn.commit()

    related = enrich_related_ads(
        store,
        "ad_a",
        text_vector=[1.0, 0.0, 0.0],
        visual_vector=[1.0, 0.0, 0.0],
        min_score=0.7,
    )

    match = related.semantically_similar[0]
    assert match.ad_id == "ad_b"
    assert match.verdict == "same_campaign_different_sku"
    assert match.text_score == 0.8
    assert match.visual_score == 1.0
    assert {diff["field"] for diff in match.differences} >= {"products", "offers"}


def test_enrich_related_ads_filters_low_scores(tmp_path):
    db = tmp_path / "filter.db"
    conn = open_database(db)
    apply_migrations(conn)
    try:
        load_sqlite_vec(conn)
    except Exception:
        pytest.skip("sqlite-vec not available")

    ads = AdRepository(conn)
    marketing = MarketingEntityRepository(conn)
    store = SqliteVecStore(conn, text_dim=3, visual_dim=3)
    store.ensure_tables()

    ads.create(AdRecord(id="ad_x", source_path="x.mp4", status="completed"))
    ads.create(AdRecord(id="ad_y", source_path="y.mp4", status="completed"))
    marketing.upsert(
        "ad_x",
        MarketingEntities(brand=BrandEntity(name="Nike"), products=["Air Max"]),
    )
    marketing.upsert(
        "ad_y",
        MarketingEntities(brand=BrandEntity(name="Toyota"), products=["Camry"]),
    )
    store.upsert_text("ad_x", [1.0, 0.0, 0.0])
    store.upsert_text("ad_y", [0.1, 0.9, 0.5])
    store.upsert_visual("ad_x", [1.0, 0.0, 0.0])
    store.upsert_visual("ad_y", [0.1, 0.9, 0.5])
    conn.commit()

    related = enrich_related_ads(
        store,
        "ad_x",
        text_vector=[1.0, 0.0, 0.0],
        visual_vector=[1.0, 0.0, 0.0],
        min_score=0.0,
    )

    low_matches = [r for r in related.semantically_similar if r.overall_score < 0.70]
    assert len(low_matches) == 0


def test_enrich_related_ads_subcategory_peer(tmp_path):
    db = tmp_path / "peer.db"
    conn = open_database(db)
    apply_migrations(conn)
    try:
        load_sqlite_vec(conn)
    except Exception:
        pytest.skip("sqlite-vec not available")

    ads = AdRepository(conn)
    marketing = MarketingEntityRepository(conn)
    store = SqliteVecStore(conn, text_dim=3, visual_dim=3)
    store.ensure_tables()

    ads.create(AdRecord(id="ad_p1", source_path="p1.mp4", status="completed"))
    ads.create(AdRecord(id="ad_p2", source_path="p2.mp4", status="completed"))
    marketing.upsert(
        "ad_p1",
        MarketingEntities(brand=BrandEntity(name="Jeep"), subcategory="SUV", products=["Grand Cherokee"]),
    )
    marketing.upsert(
        "ad_p2",
        MarketingEntities(brand=BrandEntity(name="Ford"), subcategory="SUV", products=["Explorer"]),
    )
    store.upsert_text("ad_p1", [1.0, 0.0, 0.0])
    store.upsert_text("ad_p2", [0.85, 0.5, 0.2])
    store.upsert_visual("ad_p1", [1.0, 0.0, 0.0])
    store.upsert_visual("ad_p2", [0.9, 0.3, 0.1])
    conn.commit()

    related = enrich_related_ads(
        store,
        "ad_p1",
        text_vector=[1.0, 0.0, 0.0],
        visual_vector=[1.0, 0.0, 0.0],
        min_score=0.7,
    )

    match = related.semantically_similar[0]
    assert match.ad_id == "ad_p2"
    assert match.verdict == "similar_messaging_different_brand"
