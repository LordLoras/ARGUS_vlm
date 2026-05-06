export type AdRecord = {
  id: string;
  source_path: string;
  ingested_at?: string | null;
  duration_ms?: number | null;
  width?: number | null;
  height?: number | null;
  fps?: number | null;
  status?: string | null;
  brand_name?: string | null;
  brand_confidence?: number | null;
  products_text?: string | null;
  primary_category?: string | null;
  decision?: string | null;
  source_hash?: string | null;
  phash_mean?: string | null;
};

export type EvidenceItem = {
  time_ms?: number | null;
  frame_index?: number | null;
  source?: string | null;
  text?: string | null;
  bbox?: number[] | null;
  confidence?: number | null;
  reason?: string | null;
};

export type ClassificationRecord = {
  ad_id: string;
  primary_category?: string | null;
  risk_labels?: string[];
  confidence?: number | null;
  decision?: string | null;
  needs_human_review?: boolean | null;
  evidence?: EvidenceItem[];
  ocr_quality?: {
    overall?: string | null;
    possible_errors?: unknown[];
    missed_text?: unknown[];
  } | null;
};

export type MarketingEntities = {
  ad_id?: string;
  entities?: {
    brand?: {
      name?: string | null;
      logo_present?: boolean | null;
      logo_evidence?: unknown[];
      tagline?: string | null;
    };
    products?: string[];
    prices?: Array<{
      amount?: number | null;
      currency?: string | null;
      frame_index?: number | null;
      time_ms?: number | null;
    }>;
    offers?: Array<{
      type?: string | null;
      value?: string | null;
      expiry_text?: string | null;
      scarcity_signals?: string[];
      urgency_signals?: string[];
    }>;
    ctas?: Array<{
      text?: string | null;
      destination_hint?: string | null;
      time_ms?: number | null;
      frame_index?: number | null;
    }>;
    social_proof?: {
      rating?: number | null;
      rating_count?: string | number | null;
      testimonials?: string[];
      badges?: string[];
    };
    disclaimers?: Array<{
      text?: string | null;
      time_ms?: number | null;
      frame_index?: number | null;
      is_small_print?: boolean | null;
    }>;
    creative_format?: {
      aspect_ratio?: string | null;
      duration_ms?: number | null;
      has_voiceover?: boolean | null;
      has_on_screen_text?: boolean | null;
    };
  };
};

export type Campaign = {
  id: string;
  name: string;
  advertiser?: string | null;
  brand?: string | null;
  theme?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  description?: string | null;
  created_by?: string | null;
};

export type AdDetail = {
  ad: AdRecord;
  classification?: ClassificationRecord | null;
  marketing_entities?: MarketingEntities | null;
  campaigns?: Campaign[];
};

export type FrameRecord = {
  id?: number;
  ad_id: string;
  frame_index: number;
  time_ms: number;
  path: string;
  kept?: boolean | number;
};

export type JobRecord = {
  id: string;
  ad_id: string;
  state: string;
  progress?: number | null;
  message?: string | null;
  error?: string | null;
};

export type JobStreamEvent =
  | {
      type: "job";
      job_id: string;
      state: string;
      progress?: number | null;
      message?: string | null;
      error?: string | null;
    }
  | { type: "done"; state: string }
  | { type: "error"; message: string };

export type RelatedAd = {
  ad_id: string;
  overall_score?: number | null;
  visual_score?: number | null;
  text_score?: number | null;
  verdict?: string | null;
  differences?: unknown[];
};

export type RelatedAds = {
  exact_duplicate_of?: string | null;
  near_duplicate_of?: string | null;
  semantically_similar?: RelatedAd[];
};

export type SearchHit = {
  ad_id: string;
  score?: number | null;
  distance?: number | null;
  source?: string | null;
};

export type AgentSession = {
  id: string;
  title?: string | null;
  token_count?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type AgentMessage = {
  id?: string;
  role: "user" | "assistant" | "tool";
  content?: string | null;
  tool_name?: string | null;
  payload?: unknown;
  created_at?: string | null;
};

export type AgentStreamEvent =
  | { type: "tool_call"; name: string; args: unknown }
  | { type: "tool_result"; name: string; rows?: number; truncated?: boolean; summary?: string; result?: unknown }
  | { type: "token"; text: string }
  | { type: "done" }
  | { type: "error"; message: string };
