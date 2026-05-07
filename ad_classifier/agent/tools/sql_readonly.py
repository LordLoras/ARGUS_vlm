from __future__ import annotations

import re
from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|"
    r"replace|pragma|vacuum|reindex|truncate|grant|revoke|begin|commit|"
    r"rollback|savepoint|release)\b",
    re.IGNORECASE,
)
_MULTI_STATEMENT = re.compile(r";\s*\S")


class SqlReadonlyTool(AgentTool):
    name = "sql_readonly"
    description = (
        "Run a single read-only SELECT against the local SQLite DB. Use as a last "
        "resort — prefer list_ads, count_ads, get_ad, get_campaign, aggregate, or "
        "hybrid_search when they fit. Results are capped at the configured row limit."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A single SELECT or WITH ... SELECT statement.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 50,
                },
            },
            "required": ["sql"],
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        sql = (args.get("sql") or "").strip()
        if not sql:
            return ToolResult(name=self.name, ok=False, error="sql is required")
        if sql.endswith(";"):
            sql = sql[:-1]
        cap = ctx.config.sql_readonly_max_rows
        limit = min(int(args.get("limit", cap)), cap)

        if _MULTI_STATEMENT.search(sql):
            return ToolResult(
                name=self.name, ok=False, error="multiple statements are not allowed"
            )
        head = sql.lstrip().split(None, 1)[0].lower() if sql.lstrip() else ""
        if head not in ("select", "with"):
            return ToolResult(
                name=self.name,
                ok=False,
                error="only SELECT or WITH ... SELECT statements are allowed",
            )
        if _FORBIDDEN.search(sql):
            return ToolResult(
                name=self.name,
                ok=False,
                error="forbidden keyword detected — sql_readonly is read-only",
            )

        # query_only is already enforced on the connection. We still wrap the
        # statement in LIMIT to bound payloads when the model forgets.
        wrapped = f"SELECT * FROM ({sql}) AS subq LIMIT ?"
        try:
            rows = ctx.conn.execute(wrapped, (limit + 1,)).fetchall()
        except Exception as exc:  # pragma: no cover - sqlite varies error wording
            return ToolResult(name=self.name, ok=False, error=str(exc))

        truncated = len(rows) > limit
        rows = rows[:limit]
        data: list[dict[str, Any]] = []
        for row in rows:
            try:
                data.append(dict(zip(row.keys(), row, strict=True)))
            except AttributeError:
                data.append({f"col_{i}": v for i, v in enumerate(row)})
        return ToolResult(
            name=self.name,
            ok=True,
            data=data,
            truncated=truncated,
            row_count=len(data),
        )
