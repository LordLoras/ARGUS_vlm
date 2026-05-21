ALTER TABLE ads ADD COLUMN promotion_name TEXT;

CREATE INDEX IF NOT EXISTS idx_ads_promotion_name ON ads(promotion_name);

ALTER TABLE marketing_entities ADD COLUMN promotion_name_json TEXT;
