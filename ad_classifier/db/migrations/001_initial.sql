CREATE TABLE IF NOT EXISTS ads (
  id TEXT PRIMARY KEY,
  source_path TEXT NOT NULL,
  ingested_at TIMESTAMP NOT NULL,
  duration_ms INTEGER,
  width INTEGER,
  height INTEGER,
  fps REAL,
  status TEXT,
  brand_name TEXT,
  brand_confidence REAL,
  promotion_name TEXT,
  products_text TEXT,
  primary_category TEXT,
  decision TEXT,
  source_hash TEXT,
  phash_mean TEXT
);

CREATE INDEX IF NOT EXISTS idx_ads_brand ON ads(brand_name);
CREATE INDEX IF NOT EXISTS idx_ads_promotion_name ON ads(promotion_name);
CREATE INDEX IF NOT EXISTS idx_ads_category ON ads(primary_category);
CREATE INDEX IF NOT EXISTS idx_ads_decision ON ads(decision);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ads_source_hash ON ads(source_hash) WHERE source_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ads_phash_mean ON ads(phash_mean);

CREATE TABLE IF NOT EXISTS frames (
  id INTEGER PRIMARY KEY,
  ad_id TEXT REFERENCES ads(id) ON DELETE CASCADE,
  frame_index INTEGER NOT NULL,
  time_ms INTEGER NOT NULL,
  path TEXT NOT NULL,
  width INTEGER,
  height INTEGER,
  kept BOOLEAN NOT NULL,
  drop_reason TEXT,
  phash TEXT,
  blur_score REAL,
  UNIQUE(ad_id, frame_index)
);

CREATE TABLE IF NOT EXISTS ocr_items (
  id INTEGER PRIMARY KEY,
  frame_id INTEGER REFERENCES frames(id) ON DELETE CASCADE,
  engine TEXT NOT NULL,
  text TEXT NOT NULL,
  bbox_json TEXT,
  confidence REAL
);

CREATE TABLE IF NOT EXISTS transcript_segments (
  id INTEGER PRIMARY KEY,
  ad_id TEXT REFERENCES ads(id) ON DELETE CASCADE,
  start_ms INTEGER NOT NULL,
  end_ms INTEGER NOT NULL,
  text TEXT NOT NULL,
  confidence REAL
);

CREATE TABLE IF NOT EXISTS rule_triggers (
  id INTEGER PRIMARY KEY,
  ad_id TEXT REFERENCES ads(id) ON DELETE CASCADE,
  rule_id TEXT NOT NULL,
  category TEXT,
  risk_label TEXT,
  severity TEXT,
  evidence_text TEXT,
  time_ms INTEGER,
  frame_index INTEGER
);

CREATE TABLE IF NOT EXISTS classifications (
  ad_id TEXT PRIMARY KEY REFERENCES ads(id) ON DELETE CASCADE,
  primary_category TEXT,
  risk_labels_json TEXT,
  confidence REAL,
  decision TEXT,
  needs_human_review BOOLEAN,
  ocr_quality_json TEXT,
  vlm_raw_json TEXT,
  evidence_json TEXT,
  vlm_model TEXT NOT NULL,
  vlm_prompt_version TEXT NOT NULL,
  embedder_text_model TEXT NOT NULL,
  embedder_visual_model TEXT NOT NULL,
  pipeline_version TEXT NOT NULL,
  created_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_classifications_vlm_model ON classifications(vlm_model);
CREATE INDEX IF NOT EXISTS idx_classifications_pipeline_version ON classifications(pipeline_version);

CREATE TABLE IF NOT EXISTS marketing_entities (
  ad_id TEXT PRIMARY KEY REFERENCES ads(id) ON DELETE CASCADE,
  brand_json TEXT,
  promotion_name_json TEXT,
  products_json TEXT,
  prices_json TEXT,
  offers_json TEXT,
  ctas_json TEXT,
  social_proof_json TEXT,
  disclaimers_json TEXT,
  creative_format_json TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  ad_id TEXT REFERENCES ads(id) ON DELETE CASCADE,
  state TEXT NOT NULL,
  progress REAL,
  message TEXT,
  error TEXT,
  started_at TIMESTAMP,
  finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaigns (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  advertiser TEXT,
  brand TEXT,
  theme TEXT,
  start_date DATE,
  end_date DATE,
  created_by TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS ad_campaigns (
  ad_id TEXT REFERENCES ads(id) ON DELETE CASCADE,
  campaign_id TEXT REFERENCES campaigns(id) ON DELETE CASCADE,
  similarity_score REAL,
  assigned_by TEXT NOT NULL,
  assigned_at TIMESTAMP NOT NULL,
  PRIMARY KEY (ad_id, campaign_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS ads_fts USING fts5(
  ad_id UNINDEXED,
  brand,
  products,
  primary_category,
  transcript_text,
  ocr_text,
  marketing_entities_text,
  tokenize = 'porter unicode61'
);

CREATE TABLE IF NOT EXISTS agent_sessions (
  id TEXT PRIMARY KEY,
  created_at TIMESTAMP NOT NULL,
  user_label TEXT,
  context_json TEXT
);

CREATE TABLE IF NOT EXISTS agent_messages (
  id INTEGER PRIMARY KEY,
  session_id TEXT REFERENCES agent_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  tool_name TEXT,
  tool_args_json TEXT,
  tool_result_json TEXT,
  tokens_in INTEGER,
  tokens_out INTEGER,
  created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_frames_ad ON frames(ad_id);
CREATE INDEX IF NOT EXISTS idx_ocr_frame ON ocr_items(frame_id);
CREATE INDEX IF NOT EXISTS idx_transcript_ad ON transcript_segments(ad_id);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
CREATE INDEX IF NOT EXISTS idx_ad_campaigns_ad ON ad_campaigns(ad_id);
CREATE INDEX IF NOT EXISTS idx_ad_campaigns_campaign ON ad_campaigns(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_brand ON campaigns(brand);
CREATE INDEX IF NOT EXISTS idx_agent_messages_session ON agent_messages(session_id);
