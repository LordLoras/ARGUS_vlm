ALTER TABLE ads ADD COLUMN iab_unique_id TEXT;
ALTER TABLE ads ADD COLUMN iab_parent_id TEXT;
ALTER TABLE ads ADD COLUMN iab_tier_1 TEXT;
ALTER TABLE ads ADD COLUMN iab_tier_2 TEXT;
ALTER TABLE ads ADD COLUMN iab_tier_3 TEXT;
ALTER TABLE ads ADD COLUMN iab_selected_depth INTEGER;
ALTER TABLE ads ADD COLUMN iab_selected_category TEXT;
ALTER TABLE ads ADD COLUMN iab_full_path TEXT;
ALTER TABLE ads ADD COLUMN iab_confidence TEXT;

CREATE INDEX IF NOT EXISTS idx_ads_iab_unique_id ON ads(iab_unique_id);
CREATE INDEX IF NOT EXISTS idx_ads_iab_full_path ON ads(iab_full_path);
CREATE INDEX IF NOT EXISTS idx_ads_iab_tier_1 ON ads(iab_tier_1);

ALTER TABLE classifications ADD COLUMN iab_category_json TEXT;
