ALTER TABLE ads ADD COLUMN duplicate_of TEXT;
ALTER TABLE ads ADD COLUMN duplicate_verdict TEXT;
ALTER TABLE ads ADD COLUMN duplicate_score REAL;

CREATE INDEX IF NOT EXISTS idx_ads_duplicate_of ON ads(duplicate_of);
