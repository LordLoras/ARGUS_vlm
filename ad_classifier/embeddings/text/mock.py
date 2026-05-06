from __future__ import annotations

import hashlib
import math

from ad_classifier.embeddings.text.base import TextEmbedder

_DIM = 384


class MockTextEmbedder(TextEmbedder):
    """Deterministic embedder that returns a unit-norm vector derived from the text hash."""

    def __init__(self, dim: int = _DIM) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return "mock-text-embedder"

    def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        # Expand digest to required dim by repeating + truncating
        raw = (digest * (self._dim // len(digest) + 1))[: self._dim]
        floats = [(b / 127.5) - 1.0 for b in raw]
        # Normalise to unit sphere
        norm = math.sqrt(sum(x * x for x in floats)) or 1.0
        return [x / norm for x in floats]
