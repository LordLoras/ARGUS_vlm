from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext
from ad_classifier.db.repositories import AdCampaignRepository, CampaignRepository


class GetCampaignTool(AgentTool):
    name = "get_campaign"
    description = (
        "Fetch a campaign by campaign_id with the list of assigned ads. "
        "Use list_campaigns first to discover ids."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"campaign_id": {"type": "string"}},
            "required": ["campaign_id"],
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        campaign_id = args.get("campaign_id")
        if not campaign_id:
            return ToolResult(name=self.name, ok=False, error="campaign_id is required")

        campaign = CampaignRepository(ctx.conn).get(campaign_id)
        if campaign is None:
            return ToolResult(
                name=self.name, ok=False, error=f"campaign not found: {campaign_id}"
            )
        ads = AdCampaignRepository(ctx.conn).list_for_campaign(campaign_id)
        return ToolResult(
            name=self.name,
            ok=True,
            data={
                "campaign": campaign.model_dump(mode="json"),
                "ads": [a.model_dump(mode="json") for a in ads],
            },
            row_count=len(ads),
        )


class ListCampaignsTool(AgentTool):
    name = "list_campaigns"
    description = (
        "List campaigns filtered by brand or text substring. Returns id, name, "
        "brand, theme, created_by ('auto' or 'user')."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "brand": {"type": "string"},
                "created_by": {"type": "string", "enum": ["auto", "user"]},
                "q": {"type": "string", "description": "Substring on name/description/theme."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        cap = ctx.config.list_max_rows
        limit = min(int(args.get("limit", 25)), cap)
        offset = max(int(args.get("offset", 0)), 0)
        repo = CampaignRepository(ctx.conn)
        rows = repo.list(
            brand=args.get("brand"),
            created_by=args.get("created_by"),
            q=args.get("q"),
            limit=limit + 1,
            offset=offset,
        )
        truncated = len(rows) > limit
        rows = rows[:limit]
        return ToolResult(
            name=self.name,
            ok=True,
            data=[
                {
                    "campaign_id": c.id,
                    "name": c.name,
                    "brand": c.brand,
                    "theme": c.theme,
                    "created_by": c.created_by,
                }
                for c in rows
            ],
            truncated=truncated,
            row_count=len(rows),
        )
