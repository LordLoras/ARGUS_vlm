from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from ad_classifier.campaigns.research_helpers import (
    campaign_suggestion_values,
    clean,
    creative_bool,
    creative_value,
    date_range,
    first_count,
    first_value,
    json_dict,
    json_list,
    json_value,
    mean,
    price_values,
    small_print_count,
    span_days,
    split_products,
    string_values,
    text_values,
    top_counts,
)
from ad_classifier.db.repositories.base import row_to_dict
from ad_classifier.models.campaigns import CampaignRecord


def campaign_rollup(conn: sqlite3.Connection, campaign: CampaignRecord) -> dict[str, Any]:
    payload = campaign.model_dump(mode="json")
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS ad_count,
          AVG(similarity_score) AS mean_similarity,
          MIN(ads.ingested_at) AS first_seen,
          MAX(ads.ingested_at) AS last_seen
        FROM ad_campaigns
        LEFT JOIN ads ON ads.id = ad_campaigns.ad_id
        WHERE ad_campaigns.campaign_id = ?
        """,
        (campaign.id,),
    ).fetchone()
    payload["ad_count"] = int(row["ad_count"] or 0)
    payload["mean_similarity"] = row["mean_similarity"]
    payload["first_seen"] = row["first_seen"]
    payload["last_seen"] = row["last_seen"]
    return payload


def campaign_detail(conn: sqlite3.Connection, campaign: CampaignRecord) -> dict[str, Any]:
    ad_rows = _campaign_ad_rows(conn, campaign.id)
    ads = [_ad_payload(row) for row in ad_rows]
    return {
        "campaign": campaign_rollup(conn, campaign),
        "ads": ads,
        "research": _research_payload(campaign, ads),
    }


def _campaign_ad_rows(conn: sqlite3.Connection, campaign_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          ac.ad_id,
          ac.campaign_id,
          ac.similarity_score,
          ac.assigned_by,
          ac.assigned_at,
          ads.source_path,
          ads.ingested_at,
          ads.duration_ms,
          ads.status,
          ads.brand_name,
          ads.advertiser_name,
          ads.products_text,
          ads.primary_category,
          ads.subcategory,
          classifications.confidence,
          classifications.risk_labels_json,
          marketing_entities.products_json,
          marketing_entities.prices_json,
          marketing_entities.offers_json,
          marketing_entities.ctas_json,
          marketing_entities.disclaimers_json,
          marketing_entities.creative_format_json,
          marketing_entities.creative_attributes_json,
          marketing_entities.campaign_suggestions_json
        FROM ad_campaigns ac
        LEFT JOIN ads ON ads.id = ac.ad_id
        LEFT JOIN classifications ON classifications.ad_id = ac.ad_id
        LEFT JOIN marketing_entities ON marketing_entities.ad_id = ac.ad_id
        WHERE ac.campaign_id = ?
        ORDER BY ac.assigned_at DESC, ac.ad_id
        """,
        (campaign_id,),
    ).fetchall()
    return [row_to_dict(row) or {} for row in rows]


def _ad_payload(row: dict[str, Any]) -> dict[str, Any]:
    products = string_values(json_value(row.get("products_json")))
    if not products:
        products = split_products(row.get("products_text"))

    offers = text_values(json_value(row.get("offers_json")))
    ctas = text_values(json_value(row.get("ctas_json")))
    prices = price_values(json_value(row.get("prices_json")))
    disclaimers = json_list(row.get("disclaimers_json"))
    creative_format = json_dict(row.get("creative_format_json"))
    creative_attributes = json_dict(row.get("creative_attributes_json"))
    campaign_suggestions = json_list(row.get("campaign_suggestions_json"))

    return {
        "ad_id": row.get("ad_id"),
        "campaign_id": row.get("campaign_id"),
        "similarity_score": row.get("similarity_score"),
        "assigned_by": row.get("assigned_by"),
        "assigned_at": row.get("assigned_at"),
        "source_path": row.get("source_path"),
        "ingested_at": row.get("ingested_at"),
        "duration_ms": row.get("duration_ms"),
        "status": row.get("status"),
        "brand_name": row.get("brand_name"),
        "advertiser_name": row.get("advertiser_name"),
        "products": products,
        "products_text": row.get("products_text"),
        "primary_category": row.get("primary_category"),
        "subcategory": row.get("subcategory"),
        "confidence": row.get("confidence"),
        "risk_labels": string_values(json_value(row.get("risk_labels_json"))),
        "offers": offers,
        "ctas": ctas,
        "prices": prices,
        "disclaimer_count": len(disclaimers),
        "small_print_count": small_print_count(disclaimers),
        "creative_format": creative_format,
        "creative_attributes": creative_attributes,
        "campaign_suggestions": campaign_suggestion_values(campaign_suggestions),
    }


def _research_payload(campaign: CampaignRecord, ads: list[dict[str, Any]]) -> dict[str, Any]:
    ad_count = len(ads)
    confidence_values = [
        float(ad["confidence"]) for ad in ads if isinstance(ad.get("confidence"), int | float)
    ]
    first_seen, last_seen = date_range([ad.get("ingested_at") for ad in ads])
    assignments = Counter(clean(ad.get("assigned_by")) for ad in ads if clean(ad.get("assigned_by")))

    summary = {
        "ad_count": ad_count,
        "user_assigned": assignments.get("user", 0),
        "auto_assigned": assignments.get("auto", 0),
        "mean_similarity": mean(
            [
                float(ad["similarity_score"])
                for ad in ads
                if isinstance(ad.get("similarity_score"), int | float)
            ]
        ),
        "avg_confidence": mean(confidence_values),
        "min_confidence": min(confidence_values) if confidence_values else None,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "span_days": span_days(first_seen, last_seen),
        "brands": top_counts(ad.get("brand_name") for ad in ads),
        "advertisers": top_counts(ad.get("advertiser_name") for ad in ads),
        "categories": top_counts(ad.get("primary_category") for ad in ads),
        "subcategories": top_counts(ad.get("subcategory") for ad in ads),
    }

    messaging = {
        "top_products": top_counts(value for ad in ads for value in ad.get("products", [])),
        "top_offers": top_counts(value for ad in ads for value in ad.get("offers", [])),
        "top_ctas": top_counts(value for ad in ads for value in ad.get("ctas", [])),
        "top_prices": top_counts(value for ad in ads for value in ad.get("prices", [])),
        "campaign_signals": top_counts(
            value for ad in ads for value in ad.get("campaign_suggestions", [])
        ),
    }

    creative = {
        "aspect_ratios": top_counts(
            creative_value(ad, "aspect_ratio", "aspect_ratio") for ad in ads
        ),
        "formats": top_counts(creative_value(ad, None, "format") for ad in ads),
        "voiceover_ads": sum(1 for ad in ads if creative_bool(ad, "has_voiceover", "voiceover")),
        "on_screen_text_ads": sum(
            1 for ad in ads if creative_bool(ad, "has_on_screen_text", None)
        ),
        "disclaimer_ads": sum(1 for ad in ads if int(ad.get("disclaimer_count") or 0) > 0),
        "small_print_ads": sum(1 for ad in ads if int(ad.get("small_print_count") or 0) > 0),
        "disclaimer_density": top_counts(
            (ad.get("creative_attributes") or {}).get("disclaimer_density") for ad in ads
        ),
    }

    watchouts = {
        "risk_labels": top_counts(value for ad in ads for value in ad.get("risk_labels", [])),
        "disclaimer_count": sum(int(ad.get("disclaimer_count") or 0) for ad in ads),
        "small_print_count": sum(int(ad.get("small_print_count") or 0) for ad in ads),
        "low_confidence_ads": [
            ad.get("ad_id")
            for ad in ads
            if isinstance(ad.get("confidence"), int | float) and float(ad["confidence"]) < 0.65
        ],
    }

    insights = _insights(campaign, summary, messaging, creative, watchouts)
    return {
        "summary": summary,
        "messaging": messaging,
        "creative": creative,
        "watchouts": watchouts,
        "insights": insights,
        "research_prompts": _research_prompts(campaign, summary, messaging, watchouts),
    }


def _insights(
    campaign: CampaignRecord,
    summary: dict[str, Any],
    messaging: dict[str, Any],
    creative: dict[str, Any],
    watchouts: dict[str, Any],
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    ad_count = int(summary["ad_count"] or 0)
    if ad_count == 0:
        return [
            {
                "kind": "coverage",
                "title": "No assigned ads",
                "detail": "Assign ads manually or accept a discovery proposal before analyzing this campaign.",
            }
        ]

    top_signal = first_value(messaging["campaign_signals"])
    if top_signal:
        insights.append(
            {
                "kind": "campaign_signal",
                "title": "Repeated campaign language",
                "detail": f"{top_signal} appears as an extracted campaign signal across assigned ads.",
            }
        )

    top_offer = first_count(messaging["top_offers"])
    if top_offer:
        insights.append(
            {
                "kind": "offer",
                "title": "Dominant offer",
                "detail": f"{top_offer['value']} appears in {top_offer['count']} of {ad_count} ads.",
            }
        )

    top_cta = first_count(messaging["top_ctas"])
    if top_cta and int(top_cta["count"]) >= max(2, ad_count // 2):
        insights.append(
            {
                "kind": "cta",
                "title": "CTA consistency",
                "detail": f"{top_cta['value']} is the leading call to action across the campaign.",
            }
        )

    product_count = len(messaging["top_products"])
    if product_count >= 2:
        insights.append(
            {
                "kind": "product_mix",
                "title": "Variant mix",
                "detail": f"{product_count} products or SKUs appear, useful for comparing campaign variants.",
            }
        )

    if int(creative["disclaimer_ads"]) > 0:
        insights.append(
            {
                "kind": "disclaimer",
                "title": "Fine-print footprint",
                "detail": (
                    f"{creative['disclaimer_ads']} ads include disclaimers; "
                    f"{creative['small_print_ads']} have small-print markers."
                ),
            }
        )

    top_risk = first_count(watchouts["risk_labels"])
    if top_risk:
        insights.append(
            {
                "kind": "observation",
                "title": "Observation tag pattern",
                "detail": f"{top_risk['value']} appears in {top_risk['count']} assigned ads.",
            }
        )

    if not campaign.brand and not summary["brands"]:
        insights.append(
            {
                "kind": "metadata_gap",
                "title": "Brand metadata gap",
                "detail": "No campaign brand or ad-level brand appears in the assigned set.",
            }
        )

    return insights[:6]


def _research_prompts(
    campaign: CampaignRecord,
    summary: dict[str, Any],
    messaging: dict[str, Any],
    watchouts: dict[str, Any],
) -> list[str]:
    name = campaign.name
    prompts = [
        f"Compare the ads in {name} by product, offer, and CTA.",
        f"Which ads in {name} have the strongest fine-print or disclaimer burden?",
    ]
    if messaging["top_products"]:
        prompts.append(f"Which {name} variants mention different products or SKUs?")
    if watchouts["risk_labels"]:
        prompts.append(f"Summarize observation tags across {name} and cite ad ids.")
    elif summary["categories"]:
        prompts.append(f"What category mix does {name} cover, and are there outliers?")
    return prompts[:4]
