from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext


class CountAdsTool(AgentTool):
    name = "count_ads"
    description = (
        "Count ads matching brand / primary_category / status filters. "
        "Use this for 'how many' questions instead of list_ads."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "brand": {"type": "string"},
                "category": {"type": "string"},
                "status": {"type": "string"},
            },
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        clauses: list[str] = []
        params: list[Any] = []
        if args.get("brand"):
            clauses.append("brand_name = ?")
            params.append(args["brand"])
        if args.get("category"):
            clauses.append("primary_category = ?")
            params.append(args["category"])
        if args.get("status"):
            clauses.append("status = ?")
            params.append(args["status"])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        row = ctx.conn.execute(f"SELECT COUNT(*) FROM ads {where}", params).fetchone()
        count = int(row[0]) if row else 0
        return ToolResult(
            name=self.name,
            ok=True,
            data={"count": count, "filters": {k: v for k, v in args.items() if v}},
            row_count=1,
        )
