from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext

_ALLOWED_GROUP = {
    "brand_name",
    "primary_category",
    "status",
    "advertiser_name",
    "iab_tier_1",
    "iab_selected_category",
    "iab_full_path",
}


class AggregateTool(AgentTool):
    name = "aggregate"
    description = (
        "Group ads by an allowed dimension (brand_name, primary_category, status, "
        "advertiser_name, iab_tier_1, iab_selected_category, iab_full_path) and return a count per group. Use this for 'top N "
        "brands' or 'how many ads per category' questions."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "string",
                    "enum": sorted(_ALLOWED_GROUP),
                },
                "filter_brand": {"type": "string"},
                "filter_category": {"type": "string"},
                "filter_status": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            },
            "required": ["group_by"],
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        group_by = args.get("group_by")
        if group_by not in _ALLOWED_GROUP:
            return ToolResult(
                name=self.name,
                ok=False,
                error=f"group_by must be one of {sorted(_ALLOWED_GROUP)}",
            )

        clauses: list[str] = []
        params: list[Any] = []
        if args.get("filter_brand"):
            clauses.append("brand_name = ?")
            params.append(args["filter_brand"])
        if args.get("filter_category"):
            clauses.append("primary_category = ?")
            params.append(args["filter_category"])
        if args.get("filter_status"):
            clauses.append("status = ?")
            params.append(args["filter_status"])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cap = ctx.config.list_max_rows
        limit = min(int(args.get("limit", 25)), cap)
        rows = ctx.conn.execute(
            f"""
            SELECT {group_by} AS bucket, COUNT(*) AS total
            FROM ads
            {where}
            GROUP BY {group_by}
            ORDER BY total DESC, bucket IS NULL, bucket
            LIMIT ?
            """,
            (*params, limit + 1),
        ).fetchall()
        truncated = len(rows) > limit
        rows = rows[:limit]
        return ToolResult(
            name=self.name,
            ok=True,
            data=[{"bucket": r[0], "count": int(r[1])} for r in rows],
            truncated=truncated,
            row_count=len(rows),
        )
