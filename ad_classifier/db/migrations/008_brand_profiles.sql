CREATE TABLE IF NOT EXISTS brand_profiles (
  normalized_name TEXT PRIMARY KEY,
  query_name TEXT NOT NULL,
  display_name TEXT,
  description TEXT,
  summary TEXT,
  wikipedia_title TEXT,
  wikipedia_url TEXT,
  wikipedia_page_id INTEGER,
  wikidata_qid TEXT,
  parent_companies_json TEXT,
  owners_json TEXT,
  corporate_chain_json TEXT,
  industries_json TEXT,
  official_website TEXT,
  headquarters_json TEXT,
  countries_json TEXT,
  inception TEXT,
  founded_by_json TEXT,
  subsidiaries_json TEXT,
  key_metrics_json TEXT,
  lookup_steps_json TEXT,
  source_urls_json TEXT,
  source_json TEXT,
  fetched_at TIMESTAMP NOT NULL,
  expires_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_brand_profiles_qid ON brand_profiles(wikidata_qid);
CREATE INDEX IF NOT EXISTS idx_brand_profiles_display_name ON brand_profiles(display_name);
