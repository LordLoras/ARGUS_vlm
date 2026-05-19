ALTER TABLE ads ADD COLUMN iab_content_ids TEXT;
ALTER TABLE ads ADD COLUMN iab_content_paths TEXT;
ALTER TABLE ads ADD COLUMN iab_content_categories_json TEXT;

CREATE INDEX IF NOT EXISTS idx_ads_iab_content_ids ON ads(iab_content_ids);
CREATE INDEX IF NOT EXISTS idx_ads_iab_content_paths ON ads(iab_content_paths);

ALTER TABLE classifications ADD COLUMN iab_content_categories_json TEXT;
