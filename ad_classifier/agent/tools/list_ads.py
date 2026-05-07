from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext
from ad_classifier.db.repositories import AdRepository


class ListAdsTool(AgentTool):
    name = "list_ads"
    description = (
        "List ads filtered by brand, primary_category, status, or a free-text "
        "substring (matches id, brand, advertiser, products, website, phone, "
        "landing page domain). Returns products_text so product/model questions "
        "can usually be answered without get_ad. For counts, prefer count_ads."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "brand": {"type": "string", "description": "Exact brand_name match."},
                "category": {
                    "type": "string",
                    "description": "Exact primary_category match.",
                },
                "status": {
                    "type": "string",
                    "enum": [
                        "new",
                        "processing",
                        "completed",
                        "failed",
                        "duplicate",
                        "review",
                    ],
                },
                "q": {"type": "string", "description": "Free-text substring filter."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        cap = ctx.config.list_max_rows
        limit = min(int(args.get("limit", 25)), cap)
        offset = max(int(args.get("offset", 0)), 0)
        ads = AdRepository(ctx.conn).list(
            brand=args.get("brand"),
            category=args.get("category"),
            status=args.get("status"),
            q=args.get("q"),
            limit=limit + 1,
            offset=offset,
        )
        truncated = len(ads) > limit
        ads = ads[:limit]
        return ToolResult(
            name=self.name,
            ok=True,
            data=[
                {
                    "ad_id": ad.id,
                    "brand": ad.brand_name,
                    "advertiser": ad.advertiser_name,
                    "primary_category": ad.primary_category,
                    "status": ad.status,
                    "duration_ms": ad.duration_ms,
                    "products": ad.products_text,
                    "website_domain": ad.website_domain,
                    "phone_number": ad.phone_number,
                    "landing_page_domain": ad.landing_page_domain,
                    "ingested_at": ad.ingested_at.isoformat() if ad.ingested_at else None,
                }
                for ad in ads
            ],
            truncated=truncated,
            row_count=len(ads),
        )
