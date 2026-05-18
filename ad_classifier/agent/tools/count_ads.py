from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext
from ad_classifier.search.query_expansion import (
    build_loose_like_clause,
    expand_query_terms,
    has_alias_expansion,
)


class CountAdsTool(AgentTool):
    name = "count_ads"
    description = (
        "Count ads matching brand / advertiser / primary_category / subcategory / "
        "IAB taxonomy / status filters or a loose free-text q substring over id, "
        "brand, advertiser, products, category, IAB taxonomy, website, phone, and landing page domain. Use q for "
        "topic words and business shorthand such as HVAC or services. Use this for "
        "'how many' questions instead of list_ads."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "brand": {"type": "string", "description": "Exact brand_name match."},
                "advertiser": {"type": "string", "description": "Exact advertiser_name match."},
                "category": {"type": "string", "description": "Primary industry category."},
                "subcategory": {"type": "string", "description": "Product type or niche."},
                "iab_unique_id": {
                    "type": "string",
                    "description": "Exact IAB product taxonomy unique ID.",
                },
                "iab_tier_1": {"type": "string", "description": "IAB top-level taxonomy bucket."},
                "status": {"type": "string"},
                "q": {"type": "string"},
            },
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        clauses: list[str] = []
        params: list[Any] = []
        if args.get("brand"):
            clauses.append("brand_name = ?")
            params.append(args["brand"])
        if args.get("advertiser"):
            clauses.append("LOWER(advertiser_name) = LOWER(?)")
            params.append(args["advertiser"])
        if args.get("category"):
            if has_alias_expansion(args["category"]):
                loose_clause, loose_params = build_loose_like_clause(args["category"])
                clauses.append(f"(primary_category = ? OR {loose_clause})")
                params.append(args["category"])
                params.extend(loose_params)
            else:
                clauses.append("primary_category = ?")
                params.append(args["category"])
        if args.get("subcategory"):
            clauses.append("LOWER(subcategory) = LOWER(?)")
            params.append(args["subcategory"])
        if args.get("iab_unique_id"):
            clauses.append("iab_unique_id = ?")
            params.append(args["iab_unique_id"])
        if args.get("iab_tier_1"):
            clauses.append("LOWER(iab_tier_1) = LOWER(?)")
            params.append(args["iab_tier_1"])
        if args.get("status"):
            clauses.append("status = ?")
            params.append(args["status"])
        if args.get("q"):
            loose_clause, loose_params = build_loose_like_clause(args["q"])
            if loose_clause:
                clauses.append(loose_clause)
                params.extend(loose_params)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        row = ctx.conn.execute(f"SELECT COUNT(*) FROM ads {where}", params).fetchone()
        count = int(row[0]) if row else 0
        expanded_terms = {
            key: expand_query_terms(value)
            for key in ("category", "q")
            if (value := args.get(key)) and has_alias_expansion(value)
        }
        data: dict[str, Any] = {
            "count": count,
            "filters": {k: v for k, v in args.items() if v},
        }
        if expanded_terms:
            data["expanded_terms"] = expanded_terms
        return ToolResult(
            name=self.name,
            ok=True,
            data=data,
            row_count=1,
        )
