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
  advertiser_name?: string | null;
  website_domain?: string | null;
  phone_number?: string | null;
  landing_page_domain?: string | null;
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
  brand?: {
    name?: string | null;
    confidence?: number | null;
    logo_present?: boolean | null;
    logo_evidence?: EvidenceItem[];
    tagline?: string | null;
  };
  products?: string[];
  prices?: Array<{
    text?: string | null;
    amount?: number | null;
    currency?: string | null;
    evidence?: EvidenceItem[];
  }>;
  offers?: Array<{
    text?: string | null;
    type?: string | null;
    value?: string | null;
    expiry_text?: string | null;
    evidence?: EvidenceItem[];
  }>;
  ctas?: Array<{
    text?: string | null;
    destination_hint?: string | null;
    time_ms?: number | null;
    frame_index?: number | null;
    evidence?: EvidenceItem[];
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
    evidence?: EvidenceItem[];
  }>;
  creative_format?: {
    aspect_ratio?: string | null;
    duration_ms?: number | null;
    has_voiceover?: boolean | null;
    has_on_screen_text?: boolean | null;
  };
  contact_points?: {
    websites?: Array<{ url?: string | null; domain?: string | null; display_text?: string | null; evidence?: EvidenceItem[] }>;
    phone_numbers?: Array<{ raw?: string | null; normalized?: string | null; type?: string | null; evidence?: EvidenceItem[] }>;
    social_handles?: unknown[];
    app_store_links?: unknown[];
    qr_codes?: unknown[];
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
  rrf_score?: number | null;
  fts_rank?: number | null;
  vec_rank?: number | null;
  vec_distance?: number | null;
  source?: string | null;
  ad?: AdRecord | null;
  thumbnail_path?: string | null;
  thumbnail_time_ms?: number | null;
};

export type AgentSession = {
  id: string;
  user_label?: string | null;
  context_json?: string | null;
  created_at?: string | null;
};

export type AgentMessage = {
  id?: number | null;
  session_id?: string;
  role: "user" | "assistant" | "tool";
  content?: string | null;
  tool_name?: string | null;
  tool_args_json?: string | null;
  tool_result_json?: string | null;
  tokens_in?: number | null;
  tokens_out?: number | null;
  created_at?: string | null;
};

export type AgentStreamEvent =
  | { type: "session"; payload: { session_id: string } }
  | { type: "message"; payload: { role: "user" | "assistant"; content: string; session_id: string } }
  | {
      type: "tool_call";
      payload: {
        session_id: string;
        id: string;
        name: string;
        arguments: Record<string, unknown>;
      };
    }
  | {
      type: "tool_result";
      payload: {
        session_id: string;
        id: string;
        name: string;
        ok: boolean;
        truncated: boolean;
        row_count: number | null;
        error: string | null;
        data: unknown;
      };
    }
  | {
      type: "final";
      payload: {
        session_id: string;
        text: string;
        iterations: number;
        error: string | null;
      };
    }
  | { type: "error"; payload: { session_id: string; message: string } }
  | { type: "done"; payload: { session_id: string } };
