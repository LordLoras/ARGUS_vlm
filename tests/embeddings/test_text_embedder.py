from __future__ import annotations

import math

import pytest

from ad_classifier.embeddings.text.mock import MockTextEmbedder


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def test_mock_embed_returns_correct_dim():
    emb = MockTextEmbedder(dim=384)
    vec = emb.embed("hello world")
    assert len(vec) == 384


def test_mock_embed_is_unit_norm():
    emb = MockTextEmbedder()
    vec = emb.embed("some text")
    assert abs(_norm(vec) - 1.0) < 1e-5


def test_mock_embed_is_deterministic():
    emb = MockTextEmbedder()
    assert emb.embed("test") == emb.embed("test")


def test_mock_embed_different_texts_differ():
    emb = MockTextEmbedder()
    assert emb.embed("foo") != emb.embed("bar")


def test_mock_embed_batch():
    emb = MockTextEmbedder(dim=64)
    texts = ["a", "b", "c"]
    result = emb.embed_batch(texts)
    assert len(result) == 3
    assert all(len(v) == 64 for v in result)


def test_mock_model_name():
    emb = MockTextEmbedder()
    assert emb.model_name == "mock-text-embedder"


def test_mock_custom_dim():
    emb = MockTextEmbedder(dim=128)
    assert emb.dim == 128
    assert len(emb.embed("x")) == 128
