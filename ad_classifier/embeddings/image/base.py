from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ImageEmbedder(ABC):
    @abstractmethod
    def embed(self, path: Path) -> list[float]:
        ...

    def embed_batch(self, paths: list[Path]) -> list[list[float]]:
        return [self.embed(p) for p in paths]

    @property
    @abstractmethod
    def dim(self) -> int:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...
