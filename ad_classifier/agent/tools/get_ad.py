from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext
from ad_classifier.db.repositories import AdCampaignRepository, AdRepository
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository


class GetAdTool(AgentTool):
    name = "get_ad"
    description = (
        "Fetch a single ad by ad_id with classification, marketing entities, "
        "and campaign assignments. Returns ok=false if the id does not exist."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ad_id": {"type": "string", "description": "Exact ad id like 'ad_xxxxxxxx'."},
            },
            "required": ["ad_id"],
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        ad_id = args.get("ad_id")
        if not ad_id:
            return ToolResult(name=self.name, ok=False, error="ad_id is required")

        ad = AdRepository(ctx.conn).get(ad_id)
        if ad is None:
            return ToolResult(name=self.name, ok=False, error=f"ad not found: {ad_id}")

        classification = ClassificationRepository(ctx.conn).get(ad_id)
        marketing = MarketingEntityRepository(ctx.conn).get(ad_id)
        campaigns = AdCampaignRepository(ctx.conn).list_for_ad(ad_id)

        return ToolResult(
            name=self.name,
            ok=True,
            data={
                "ad": ad.model_dump(mode="json"),
                "classification": classification.model_dump(mode="json")
                if classification
                else None,
                "marketing_entities": marketing.model_dump(mode="json") if marketing else None,
                "campaigns": [c.model_dump(mode="json") for c in campaigns],
            },
            row_count=1,
        )
