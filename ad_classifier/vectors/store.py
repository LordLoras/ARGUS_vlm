from __future__ import annotations

import struct
from typing import Protocol, runtime_checkable


def serialize_float32(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def deserialize_float32(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


@runtime_checkable
class VectorStore(Protocol):
    def upsert_text(self, ad_id: str, vector: list[float]) -> None: ...
    def upsert_visual(self, ad_id: str, vector: list[float]) -> None: ...
    def search_text(self, query: list[float], k: int = 10) -> list[tuple[str, float]]: ...
    def search_visual(self, query: list[float], k: int = 10) -> list[tuple[str, float]]: ...
    def get_text(self, ad_id: str) -> list[float] | None: ...
    def get_visual(self, ad_id: str) -> list[float] | None: ...
    def delete(self, ad_id: str) -> None: ...
