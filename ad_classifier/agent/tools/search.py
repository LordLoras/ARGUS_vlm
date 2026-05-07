from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.search.fts import fts_search
from ad_classifier.search.hybrid import hybrid_search


class HybridSearchTool(AgentTool):
    name = "hybrid_search"
    description = (
        "Search ads by free-text query using FTS5 keyword + sentence-transformer "
        "vector similarity fused with reciprocal rank. Best for free-form questions "
        "mixing keywords with semantic meaning."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["query"],
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = (args.get("query") or "").strip()
        if not query:
            return ToolResult(name=self.name, ok=False, error="query is required")
        k = min(int(args.get("k", 10)), 50)

        # Embed the query if a text embedder factory was provided. When no
        # factory is configured (tests, or vector store unavailable), fall back
        # to FTS-only — hybrid_search handles a None vector.
        query_vector = None
        if ctx.text_embedder_factory is not None:
            try:
                embedder = ctx.text_embedder_factory()
                query_vector = embedder.embed(query)
            except Exception:
                query_vector = None

        store = None
        if ctx.vector_store_factory is not None and query_vector is not None:
            try:
                store = ctx.vector_store_factory(ctx.conn)
                load_sqlite_vec(ctx.conn)
                store.ensure_tables()
            except Exception:
                store = None

        if store is None or query_vector is None:
            # FTS5-only fallback. Still useful for keyword matches.
            try:
                hits = fts_search(ctx.conn, query, limit=k)
            except Exception as exc:
                return ToolResult(name=self.name, ok=False, error=str(exc))
            return ToolResult(
                name=self.name,
                ok=True,
                data=[{"ad_id": ad_id, "fts_score": score} for ad_id, score in hits],
                row_count=len(hits),
            )

        try:
            results = hybrid_search(
                ctx.conn,
                store,
                query_text=query,
                query_vector=query_vector,
                modality="text",
                k_fts=k * 4,
                k_vec=k * 4,
                k_final=k,
            )
        except Exception as exc:
            return ToolResult(name=self.name, ok=False, error=str(exc))

        return ToolResult(
            name=self.name,
            ok=True,
            data=[r.model_dump(mode="json") for r in results],
            row_count=len(results),
        )


class VectorSimilarityTool(AgentTool):
    name = "vector_similarity"
    description = (
        "Find ads similar to a seed ad_id using stored text or visual vectors. "
        "Use this for 'show me ads similar to ad_xxxx' questions."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ad_id": {"type": "string"},
                "modality": {"type": "string", "enum": ["text", "visual"], "default": "text"},
                "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["ad_id"],
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ad_id = args.get("ad_id")
        if not ad_id:
            return ToolResult(name=self.name, ok=False, error="ad_id is required")
        modality = args.get("modality", "text")
        if modality not in ("text", "visual"):
            return ToolResult(
                name=self.name, ok=False, error="modality must be 'text' or 'visual'"
            )
        k = min(int(args.get("k", 10)), 50)

        if ctx.vector_store_factory is None:
            return ToolResult(
                name=self.name,
                ok=False,
                error="vector store is not configured",
            )

        try:
            store = ctx.vector_store_factory(ctx.conn)
            load_sqlite_vec(ctx.conn)
            store.ensure_tables()
        except Exception as exc:
            return ToolResult(name=self.name, ok=False, error=str(exc))

        seed = store.get_text(ad_id) if modality == "text" else store.get_visual(ad_id)
        if seed is None:
            return ToolResult(
                name=self.name,
                ok=False,
                error=f"no {modality} vector stored for {ad_id}",
            )
        hits = (
            store.search_text(seed, k=k + 1)
            if modality == "text"
            else store.search_visual(seed, k=k + 1)
        )
        items = [
            {"ad_id": found_id, "distance": dist}
            for found_id, dist in hits
            if found_id != ad_id
        ][:k]
        return ToolResult(
            name=self.name,
            ok=True,
            data={"seed_ad_id": ad_id, "modality": modality, "items": items},
            row_count=len(items),
        )
