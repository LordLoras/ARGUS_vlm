from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ad_classifier.agent.models import ToolResult, ToolSpec
from ad_classifier.config import AgentConfig, SearchConfig


@dataclass
class ToolContext:
    """Per-call dependencies handed to every tool.

    The connection is read-only (PRAGMA query_only = ON). The tool must not
    open additional connections; tests rely on this so they can swap a fake
    connection without monkey-patching the DB layer.
    """

    conn: sqlite3.Connection
    config: AgentConfig
    search_config: SearchConfig = field(default_factory=SearchConfig)
    text_embedder_factory: Any | None = None
    """Optional callable returning a TextEmbedder. Lazy so unit tests don't pay
    the sentence-transformers import cost."""
    vector_store_factory: Any | None = None
    """Optional callable returning a SqliteVecStore."""
    visual_text_embedder_factory: Any | None = None
    """Optional callable returning an embedder with embed_text() for visual search."""


class AgentTool(ABC):
    name: str
    description: str

    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """Return JSON Schema for tool arguments."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters(),
        )

    @abstractmethod
    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult: ...


def truncate(rows: list[Any], limit: int) -> tuple[list[Any], bool]:
    """Cap a row list and report whether truncation happened."""
    if len(rows) <= limit:
        return rows, False
    return rows[:limit], True
