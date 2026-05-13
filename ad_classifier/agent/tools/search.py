from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.search.fts import fts_search_expanded
from ad_classifier.search.hybrid import hybrid_search
from ad_classifier.search.rrf import rrf_fuse
from ad_classifier.search.visual_query import expand_visual_query_texts, mean_pool


class HybridSearchTool(AgentTool):
    name = "hybrid_search"
    description = (
        "Search ads by free-text query using FTS5 keyword + vector similarity fused "
        "with reciprocal rank. Use modality=text for transcript/OCR semantics and "
        "modality=visual for cross-modal visual queries like 'red car'."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "modality": {"type": "string", "enum": ["text", "visual"], "default": "text"},
                "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["query"],
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        query = (args.get("query") or "").strip()
        if not query:
            return ToolResult(name=self.name, ok=False, error="query is required")
        modality = args.get("modality", "text")
        if modality not in ("text", "visual"):
            return ToolResult(
                name=self.name, ok=False, error="modality must be 'text' or 'visual'"
            )
        k = min(int(args.get("k", 10)), 50)

        # Embed the query if a matching embedder factory was provided. When no
        # factory is configured (tests, or vector store unavailable), fall back
        # to FTS-only — hybrid_search handles a None vector.
        query_vector = None
        if modality == "visual" and ctx.visual_text_embedder_factory is not None:
            try:
                embedder = ctx.visual_text_embedder_factory()
                texts = expand_visual_query_texts(query)
                if hasattr(embedder, "embed_text_batch"):
                    query_vector = mean_pool(embedder.embed_text_batch(texts))
                else:
                    query_vector = mean_pool([embedder.embed_text(text) for text in texts])
            except Exception:
                query_vector = None
        elif modality == "text" and ctx.text_embedder_factory is not None:
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
            except Exception:
                store = None

        if store is None or query_vector is None:
            # FTS5-only fallback. Still useful for keyword matches.
            try:
                hits = fts_search_expanded(ctx.conn, query, limit=k)
            except Exception as exc:
                return ToolResult(name=self.name, ok=False, error=str(exc))
            return ToolResult(
                name=self.name,
                ok=True,
                data=[
                    {"ad_id": ad_id, "fts_score": score, "source": "keyword"}
                    for ad_id, score in hits
                ],
                row_count=len(hits),
            )

        try:
            if modality == "visual":
                fts_results = fts_search_expanded(ctx.conn, query, limit=k * 4)
                frame_hits = store.search_frame_visual(query_vector, k=k * 4)
                visual_hits = _group_frame_hits(frame_hits)
                if not visual_hits:
                    visual_hits = [
                        {
                            "ad_id": ad_id,
                            "distance": distance,
                            "source": "visual_text",
                        }
                        for ad_id, distance in store.search_visual(query_vector, k=k * 4)
                    ]
                fused = rrf_fuse(
                    [ad_id for ad_id, _score in fts_results],
                    [hit["ad_id"] for hit in visual_hits],
                )[:k]
                visual_by_ad = {hit["ad_id"]: hit for hit in visual_hits}
                fts_rank = {
                    ad_id: index + 1 for index, (ad_id, _score) in enumerate(fts_results)
                }
                data = []
                for ad_id, rrf_score in fused:
                    item = dict(visual_by_ad.get(ad_id, {"ad_id": ad_id}))
                    item["rrf_score"] = rrf_score
                    item["fts_rank"] = fts_rank.get(ad_id)
                    item["modality"] = modality
                    item["source"] = "keyword+visual" if ad_id in visual_by_ad else "keyword"
                    data.append(item)
                return ToolResult(
                    name=self.name,
                    ok=True,
                    data=data,
                    row_count=len(data),
                )

            results = hybrid_search(
                ctx.conn,
                store,
                query_text=query,
                query_vector=query_vector,
                modality=modality,
                k_fts=k * 4,
                k_vec=k * 4,
                k_final=k,
            )
        except Exception as exc:
            return ToolResult(name=self.name, ok=False, error=str(exc))

        return ToolResult(
            name=self.name,
            ok=True,
            data=[
                {**r.model_dump(mode="json"), "modality": modality}
                for r in results
            ],
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
        except Exception as exc:
            return ToolResult(name=self.name, ok=False, error=str(exc))

        try:
            seed = store.get_text(ad_id) if modality == "text" else store.get_visual(ad_id)
        except Exception:
            seed = None
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


def _group_frame_hits(frame_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for hit in frame_hits:
        ad_id = str(hit["ad_id"])
        item = grouped.setdefault(
            ad_id,
            {
                "ad_id": ad_id,
                "distance": hit["distance"],
                "source": "visual_text",
                "matched_frames": [],
            },
        )
        item["distance"] = min(float(item["distance"]), float(hit["distance"]))
        if len(item["matched_frames"]) < 3:
            item["matched_frames"].append(
                {
                    "frame_index": hit["frame_index"],
                    "time_ms": hit["time_ms"],
                    "path": hit["path"],
                    "distance": hit["distance"],
                }
            )
    return sorted(grouped.values(), key=lambda row: float(row.get("distance", 999.0)))
