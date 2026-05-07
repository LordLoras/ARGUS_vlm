ALTER TABLE ads ADD COLUMN advertiser_name TEXT;
ALTER TABLE ads ADD COLUMN website_domain TEXT;
ALTER TABLE ads ADD COLUMN phone_number TEXT;
ALTER TABLE ads ADD COLUMN landing_page_domain TEXT;

CREATE INDEX IF NOT EXISTS idx_ads_advertiser ON ads(advertiser_name);
CREATE INDEX IF NOT EXISTS idx_ads_website_domain ON ads(website_domain);
CREATE INDEX IF NOT EXISTS idx_ads_phone_number ON ads(phone_number);
CREATE INDEX IF NOT EXISTS idx_ads_landing_page_domain ON ads(landing_page_domain);

ALTER TABLE marketing_entities ADD COLUMN contact_points_json TEXT;
ALTER TABLE marketing_entities ADD COLUMN advertiser_json TEXT;
ALTER TABLE marketing_entities ADD COLUMN landing_page_json TEXT;
ALTER TABLE marketing_entities ADD COLUMN offer_terms_json TEXT;
ALTER TABLE marketing_entities ADD COLUMN creative_attributes_json TEXT;
ALTER TABLE marketing_entities ADD COLUMN campaign_signals_json TEXT;
