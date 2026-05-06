from __future__ import annotations

import json
import sqlite3

from ad_classifier.db.repositories.base import row_to_dict
from ad_classifier.models.marketing import (
    BrandEntity,
    CTAEntity,
    CreativeFormat,
    DisclaimerEntity,
    MarketingEntities,
    OfferEntity,
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
    prices = (
        [PriceEntity.model_validate(p) for p in json.loads(prices_raw)]
        if prices_raw
        else []
    )

    offers_raw = data.get("offers_json")
    offers = (
        [OfferEntity.model_validate(o) for o in json.loads(offers_raw)]
        if offers_raw
        else []
    )

    ctas_raw = data.get("ctas_json")
    ctas = [CTAEntity.model_validate(c) for c in json.loads(ctas_raw)] if ctas_raw else []

    sp_raw = data.get("social_proof_json")
    social_proof = SocialProof.model_validate(json.loads(sp_raw)) if sp_raw else SocialProof()

    disc_raw = data.get("disclaimers_json")
    disclaimers = (
        [DisclaimerEntity.model_validate(d) for d in json.loads(disc_raw)]
        if disc_raw
        else []
    )

    cf_raw = data.get("creative_format_json")
    creative_format = (
        CreativeFormat.model_validate(json.loads(cf_raw)) if cf_raw else CreativeFormat()
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
    )


class MarketingEntityRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert(self, ad_id: str, entities: MarketingEntities) -> None:
        self.conn.execute(
            """
            INSERT INTO marketing_entities (
              ad_id, brand_json, products_json, prices_json, offers_json,
              ctas_json, social_proof_json, disclaimers_json, creative_format_json
            ) VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ad_id) DO UPDATE SET
              brand_json = excluded.brand_json,
              products_json = excluded.products_json,
              prices_json = excluded.prices_json,
              offers_json = excluded.offers_json,
              ctas_json = excluded.ctas_json,
              social_proof_json = excluded.social_proof_json,
              disclaimers_json = excluded.disclaimers_json,
              creative_format_json = excluded.creative_format_json
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
