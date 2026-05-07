from __future__ import annotations

from typing import Any

from ad_classifier.agent.models import ToolResult
from ad_classifier.agent.tools.base import AgentTool, ToolContext
from ad_classifier.db.connection import load_sqlite_vec
from ad_classifier.db.repositories import AdRepository
from ad_classifier.db.repositories.classifications import ClassificationRepository
from ad_classifier.db.repositories.marketing import MarketingEntityRepository
from ad_classifier.dedup.similarity import cosine_similarity
from ad_classifier.models.marketing import MarketingEntities
from ad_classifier.models.similarity import FieldDifference, SimilarityVerdict


def _brand_strings(entities: MarketingEntities | None) -> tuple[str | None, list[str]]:
    if entities is None:
        return None, []
    brand_name = entities.brand.name if entities.brand else None
    products = list(entities.products or [])
    return brand_name, products


def _price_strings(entities: MarketingEntities | None) -> list[str]:
    if entities is None or not entities.prices:
        return []
    return [p.text for p in entities.prices if p.text]


def _offer_strings(entities: MarketingEntities | None) -> list[str]:
    if entities is None or not entities.offers:
        return []
    return [o.text for o in entities.offers if o.text]


def _cta_strings(entities: MarketingEntities | None) -> list[str]:
    if entities is None or not entities.ctas:
        return []
    return [c.text for c in entities.ctas if c.text]


def _diff_field(field: str, left: Any, right: Any) -> FieldDifference | None:
    if left == right:
        return None
    if not left and not right:
        return None
    return FieldDifference(field=field, left=left, right=right)


def _classify_verdict(
    overall: float,
    visual: float | None,
    text: float | None,
    same_brand: bool,
    same_products: bool,
    same_offer: bool,
) -> SimilarityVerdict:
    if overall >= 0.95 and same_brand and same_products and same_offer:
        return "near_duplicate"
    if same_brand and same_products and not same_offer and overall >= 0.75:
        return "same_campaign_different_offer"
    if same_brand and not same_products and overall >= 0.75:
        return "same_campaign_different_sku"
    if not same_brand and overall >= 0.75:
        return "similar_messaging_different_brand"
    if overall >= 0.55:
        return "related"
    return "unrelated"


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


class CompareAdsTool(AgentTool):
    name = "compare_ads"
    description = (
        "Pairwise comparison of two ads by ad_id. Returns text + visual cosine "
        "similarity plus a structured field diff (brand, products, prices, offers, "
        "CTAs, primary_category) and a verdict like 'same_campaign_different_sku'."
    )

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "left_ad_id": {"type": "string"},
                "right_ad_id": {"type": "string"},
            },
            "required": ["left_ad_id", "right_ad_id"],
        }

    def call(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        left_id = args.get("left_ad_id")
        right_id = args.get("right_ad_id")
        if not left_id or not right_id:
            return ToolResult(
                name=self.name, ok=False, error="left_ad_id and right_ad_id are required"
            )
        if left_id == right_id:
            return ToolResult(name=self.name, ok=False, error="ids must differ")

        ads = AdRepository(ctx.conn)
        left_ad = ads.get(left_id)
        right_ad = ads.get(right_id)
        if left_ad is None:
            return ToolResult(name=self.name, ok=False, error=f"ad not found: {left_id}")
        if right_ad is None:
            return ToolResult(name=self.name, ok=False, error=f"ad not found: {right_id}")

        # Vector similarity (best-effort: tolerate missing vectors)
        text_score: float | None = None
        visual_score: float | None = None
        if ctx.vector_store_factory is not None:
            try:
                store = ctx.vector_store_factory(ctx.conn)
                load_sqlite_vec(ctx.conn)
                store.ensure_tables()
                lt = store.get_text(left_id)
                rt = store.get_text(right_id)
                if lt is not None and rt is not None:
                    text_score = max(0.0, min(1.0, cosine_similarity(lt, rt)))
                lv = store.get_visual(left_id)
                rv = store.get_visual(right_id)
                if lv is not None and rv is not None:
                    visual_score = max(0.0, min(1.0, cosine_similarity(lv, rv)))
            except Exception:
                # Comparing without vectors is still useful for the field diff.
                pass

        scores = [s for s in (text_score, visual_score) if s is not None]
        overall_score = sum(scores) / len(scores) if scores else 0.0

        # Structured diff
        marketing_repo = MarketingEntityRepository(ctx.conn)
        left_marketing = marketing_repo.get(left_id)
        right_marketing = marketing_repo.get(right_id)
        l_brand, l_products = _brand_strings(left_marketing)
        r_brand, r_products = _brand_strings(right_marketing)
        l_prices = _price_strings(left_marketing)
        r_prices = _price_strings(right_marketing)
        l_offers = _offer_strings(left_marketing)
        r_offers = _offer_strings(right_marketing)
        l_ctas = _cta_strings(left_marketing)
        r_ctas = _cta_strings(right_marketing)

        classifications = ClassificationRepository(ctx.conn)
        l_class = classifications.get(left_id)
        r_class = classifications.get(right_id)
        l_category = l_class.primary_category if l_class else None
        r_category = r_class.primary_category if r_class else None

        differences = [
            d
            for d in (
                _diff_field("brand", l_brand, r_brand),
                _diff_field("products", l_products, r_products),
                _diff_field("prices", l_prices, r_prices),
                _diff_field("offers", l_offers, r_offers),
                _diff_field("ctas", l_ctas, r_ctas),
                _diff_field("primary_category", l_category, r_category),
            )
            if d is not None
        ]

        same_brand = bool(l_brand) and l_brand == r_brand
        same_products = sorted(l_products) == sorted(r_products) and bool(l_products)
        same_offer = sorted(l_offers) == sorted(r_offers) and bool(l_offers)

        verdict = _classify_verdict(
            overall_score,
            visual_score,
            text_score,
            same_brand=same_brand,
            same_products=same_products,
            same_offer=same_offer,
        )

        return ToolResult(
            name=self.name,
            ok=True,
            data={
                "left_ad_id": left_id,
                "right_ad_id": right_id,
                "text_score": _round(text_score),
                "visual_score": _round(visual_score),
                "overall_score": round(overall_score, 4),
                "verdict": verdict,
                "differences": [d.model_dump() for d in differences],
            },
            row_count=1,
        )
