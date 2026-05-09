ALTER TABLE ads ADD COLUMN subcategory TEXT;

CREATE INDEX IF NOT EXISTS idx_ads_subcategory ON ads(subcategory);

ALTER TABLE marketing_entities ADD COLUMN subcategory_json TEXT;
