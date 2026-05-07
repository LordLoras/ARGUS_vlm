from __future__ import annotations

import json
import sqlite3

from ad_classifier.db.repositories.base import row_to_dict
from ad_classifier.models.marketing import (
    AdvertiserEntity,
    BrandEntity,
    CampaignSignals,
    ContactPoints,
    CreativeAttributes,
    CreativeFormat,
    CTAEntity,
    DisclaimerEntity,
    LandingPageEntity,
    MarketingEntities,
    OfferEntity,
    OfferTerms,
    PriceEntity,
    SocialProof,
)


def _to_record(row: sqlite3.Row) -> MarketingEntities:
    data = row_to_dict(row)
    assert data is not None

    brand_raw = data.get("brand_json")
    brand = BrandEntity.model_validate(json.loads(brand_raw)) if brand_raw else BrandEntity()

    products_raw = data.get("products_json")
    products: list[str] = json.loads(products_raw) if products_raw else []

    prices_raw = data.get("prices_json")
    prices = [PriceEntity.model_validate(p) for p in json.loads(prices_raw)] if prices_raw else []

    offers_raw = data.get("offers_json")
    offers = [OfferEntity.model_validate(o) for o in json.loads(offers_raw)] if offers_raw else []

    ctas_raw = data.get("ctas_json")
    ctas = [CTAEntity.model_validate(c) for c in json.loads(ctas_raw)] if ctas_raw else []

    sp_raw = data.get("social_proof_json")
    social_proof = SocialProof.model_validate(json.loads(sp_raw)) if sp_raw else SocialProof()

    disc_raw = data.get("disclaimers_json")
    disclaimers = (
        [DisclaimerEntity.model_validate(d) for d in json.loads(disc_raw)] if disc_raw else []
    )

    cf_raw = data.get("creative_format_json")
    creative_format = (
        CreativeFormat.model_validate(json.loads(cf_raw)) if cf_raw else CreativeFormat()
    )

    contact_points_raw = data.get("contact_points_json")
    contact_points = (
        ContactPoints.model_validate(json.loads(contact_points_raw))
        if contact_points_raw
        else ContactPoints()
    )

    advertiser_raw = data.get("advertiser_json")
    advertiser = (
        AdvertiserEntity.model_validate(json.loads(advertiser_raw))
        if advertiser_raw
        else AdvertiserEntity()
    )

    landing_page_raw = data.get("landing_page_json")
    landing_page = (
        LandingPageEntity.model_validate(json.loads(landing_page_raw))
        if landing_page_raw
        else LandingPageEntity()
    )

    offer_terms_raw = data.get("offer_terms_json")
    offer_terms = (
        OfferTerms.model_validate(json.loads(offer_terms_raw)) if offer_terms_raw else OfferTerms()
    )

    creative_attributes_raw = data.get("creative_attributes_json")
    creative_attributes = (
        CreativeAttributes.model_validate(json.loads(creative_attributes_raw))
        if creative_attributes_raw
        else CreativeAttributes()
    )

    campaign_signals_raw = data.get("campaign_signals_json")
    campaign_signals = (
        CampaignSignals.model_validate(json.loads(campaign_signals_raw))
        if campaign_signals_raw
        else CampaignSignals()
    )

    return MarketingEntities(
        brand=brand,
        products=products,
        prices=prices,
        offers=offers,
        ctas=ctas,
        social_proof=social_proof,
        disclaimers=disclaimers,
        creative_format=creative_format,
        contact_points=contact_points,
        advertiser=advertiser,
        landing_page=landing_page,
        offer_terms=offer_terms,
        creative_attributes=creative_attributes,
        campaign_signals=campaign_signals,
    )


class MarketingEntityRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, ad_id: str, entities: MarketingEntities) -> None:
        self.conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, prices_json, offers_json,
              ctas_json, social_proof_json, disclaimers_json, creative_format_json,
              contact_points_json, advertiser_json, landing_page_json, offer_terms_json,
              creative_attributes_json, campaign_signals_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ad_id) DO UPDATE SET
              brand_json = excluded.brand_json,
              products_json = excluded.products_json,
              prices_json = excluded.prices_json,
              offers_json = excluded.offers_json,
              ctas_json = excluded.ctas_json,
              social_proof_json = excluded.social_proof_json,
              disclaimers_json = excluded.disclaimers_json,
              creative_format_json = excluded.creative_format_json,
              contact_points_json = excluded.contact_points_json,
              advertiser_json = excluded.advertiser_json,
              landing_page_json = excluded.landing_page_json,
              offer_terms_json = excluded.offer_terms_json,
              creative_attributes_json = excluded.creative_attributes_json,
              campaign_signals_json = excluded.campaign_signals_json
            """,
            (
                ad_id,
                json.dumps(entities.brand.model_dump()),
                json.dumps(entities.products),
                json.dumps([p.model_dump() for p in entities.prices]),
                json.dumps([o.model_dump() for o in entities.offers]),
                json.dumps([c.model_dump() for c in entities.ctas]),
                json.dumps(entities.social_proof.model_dump()),
                json.dumps([d.model_dump() for d in entities.disclaimers]),
                json.dumps(entities.creative_format.model_dump()),
                json.dumps(entities.contact_points.model_dump()),
                json.dumps(entities.advertiser.model_dump()),
                json.dumps(entities.landing_page.model_dump()),
                json.dumps(entities.offer_terms.model_dump()),
                json.dumps(entities.creative_attributes.model_dump()),
                json.dumps(entities.campaign_signals.model_dump()),
            ),
        )

    def get(self, ad_id: str) -> MarketingEntities | None:
        row = self.conn.execute(
            "SELECT * FROM marketing_entities WHERE ad_id = ?", (ad_id,)
        ).fetchone()
        if row is None:
            return None
        return _to_record(row)

    def delete(self, ad_id: str) -> None:
        self.conn.execute("DELETE FROM marketing_entities WHERE ad_id = ?", (ad_id,))
