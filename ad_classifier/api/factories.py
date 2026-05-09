"""Factories for embedders and vector stores used by the agent."""

from __future__ import annotations

import sqlite3
from typing import Any

from ad_classifier.config import AppConfig
from ad_classifier.embeddings.text import SentenceTransformerEmbedder
from ad_classifier.vectors.sqlite_vec import SqliteVecStore


def text_embedder_factory(config: AppConfig) -> Any:
    """Create a text embedder instance from config."""
    cfg = config.text_embedder
    return SentenceTransformerEmbedder(model_name=cfg.model, device=cfg.device)


def vector_store_factory(config: AppConfig, conn: sqlite3.Connection) -> Any:
    """Create a vector store instance from config."""
    cfg = config.vector_store
    if cfg.backend != "sqlite-vec":
        raise ValueError(f"Unsupported vector store backend: {cfg.backend}")
    return SqliteVecStore(conn, text_dim=cfg.text_dim, visual_dim=cfg.visual_dim)
