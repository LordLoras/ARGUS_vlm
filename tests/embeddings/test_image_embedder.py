from __future__ import annotations

import math
from pathlib import Path

from ad_classifier.embeddings.image.mock import MockImageEmbedder


def _norm(v: list[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def test_mock_embed_returns_correct_dim():
    emb = MockImageEmbedder(dim=768)
    vec = emb.embed(Path("/fake/path/frame.png"))
    assert len(vec) == 768


def test_mock_embed_is_unit_norm():
    emb = MockImageEmbedder()
    vec = emb.embed(Path("/some/path.jpg"))
    assert abs(_norm(vec) - 1.0) < 1e-5


def test_mock_embed_is_deterministic():
    emb = MockImageEmbedder()
    p = Path("/a/b/c.png")
    assert emb.embed(p) == emb.embed(p)


def test_mock_embed_different_paths_differ():
    emb = MockImageEmbedder()
    assert emb.embed(Path("/a/1.png")) != emb.embed(Path("/b/2.png"))


def test_mock_embed_batch():
    emb = MockImageEmbedder(dim=32)
    paths = [Path(f"/f/{i}.png") for i in range(4)]
    result = emb.embed_batch(paths)
    assert len(result) == 4
    assert all(len(v) == 32 for v in result)


def test_mock_model_name():
    assert MockImageEmbedder().model_name == "mock-image-embedder"
