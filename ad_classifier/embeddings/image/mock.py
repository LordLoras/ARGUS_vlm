from __future__ import annotations

import hashlib
import math
from pathlib import Path

from ad_classifier.embeddings.image.base import ImageEmbedder

_DIM = 768


class MockImageEmbedder(ImageEmbedder):
    """Deterministic embedder based on file path hash — no actual image loading."""

    def __init__(self, dim: int = _DIM) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return "mock-image-embedder"

    def embed(self, path: Path) -> list[float]:
        digest = hashlib.sha256(str(path).encode()).digest()
        raw = (digest * (self._dim // len(digest) + 1))[: self._dim]
        floats = [(b / 127.5) - 1.0 for b in raw]
        norm = math.sqrt(sum(x * x for x in floats)) or 1.0
        return [x / norm for x in floats]
