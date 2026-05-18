from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext
from ad_classifier.db.repositories import AdRepository


class ListAdsTool(AgentTool):
    name = "list_ads"
    description = (
        "List ads filtered by brand, advertiser, primary_category, subcategory, "
        "status, or a free-text substring (matches id, brand, advertiser, products, "
        "category, IAB product taxonomy, website, phone, landing page domain; expands common shorthand "
        "such as HVAC or services). Returns products_text so product/model questions "
        "can usually be answered without get_ad. For counts, prefer count_ads."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "brand": {"type": "string", "description": "Exact brand_name match."},
                "advertiser": {
                    "type": "string",
                    "description": "Exact advertiser_name match (e.g. dealer, store, or business placing the ad).",
                },
                "category": {"type": "string", "description": "Primary industry category."},
                "subcategory": {
                    "type": "string",
                    "description": "Product type or niche (e.g. SUV, smartphone, pizza, credit card).",
                },
                "iab_unique_id": {
                    "type": "string",
                    "description": "Exact IAB product taxonomy unique ID.",
                },
                "iab_tier_1": {"type": "string", "description": "IAB top-level taxonomy bucket."},
                "status": {
                    "type": "string",
                    "enum": [
                        "new",
                        "processing",
                        "completed",
                        "failed",
                        "duplicate",
                    ],
                },
                "q": {"type": "string", "description": "Free-text topic filter."},
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
            advertiser=args.get("advertiser"),
            category=args.get("category"),
            subcategory=args.get("subcategory"),
            iab_unique_id=args.get("iab_unique_id"),
            iab_tier_1=args.get("iab_tier_1"),
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
                    "subcategory": ad.subcategory,
                    "iab_unique_id": ad.iab_unique_id,
                    "iab_full_path": ad.iab_full_path,
                    "iab_selected_category": ad.iab_selected_category,
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
