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
  subcategory?: string | null;
  iab_unique_id?: string | null;
  iab_parent_id?: string | null;
  iab_tier_1?: string | null;
  iab_tier_2?: string | null;
  iab_tier_3?: string | null;
  iab_selected_depth?: number | null;
  iab_selected_category?: string | null;
  iab_full_path?: string | null;
  iab_confidence?: string | null;
  source_hash?: string | null;
  phash_mean?: string | null;
  duplicate_of?: string | null;
  duplicate_verdict?: string | null;
  duplicate_score?: number | null;
};

export type IABCategory = {
  iab_unique_id: string;
  iab_parent_id?: string | null;
  tier_1?: string | null;
  tier_2?: string | null;
  tier_3?: string | null;
  selected_depth: number;
  selected_category: string;
  full_path: string;
  confidence?: string | null;
  parent_categories?: Array<{
    iab_unique_id: string;
    name: string;
    depth: number;
    full_path: string;
  }>;
  alternative_categories?: Array<{
    iab_unique_id: string;
    full_path: string;
    use_when?: string | null;
  }>;
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
  iab_category?: IABCategory | null;
  risk_labels?: string[];
  confidence?: number | null;
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
  subcategory?: string | null;
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
  ad_count?: number | null;
  mean_similarity?: number | null;
  first_seen?: string | null;
  last_seen?: string | null;
};

export type CampaignCount = {
  value: string;
  count: number;
  share?: number | null;
};

export type CampaignInsight = {
  kind?: string | null;
  title: string;
  detail: string;
};

export type CampaignAd = {
  ad_id: string;
  campaign_id?: string | null;
  similarity_score?: number | null;
  assigned_by?: string | null;
  assigned_at?: string | null;
  source_path?: string | null;
  ingested_at?: string | null;
  duration_ms?: number | null;
  status?: string | null;
  brand_name?: string | null;
  advertiser_name?: string | null;
  products?: string[];
  products_text?: string | null;
  primary_category?: string | null;
  subcategory?: string | null;
  confidence?: number | null;
  risk_labels?: string[];
  offers?: string[];
  ctas?: string[];
  prices?: string[];
  disclaimer_count?: number | null;
  small_print_count?: number | null;
};

export type CampaignResearch = {
  summary: {
    ad_count: number;
    user_assigned?: number;
    auto_assigned?: number;
    mean_similarity?: number | null;
    avg_confidence?: number | null;
    min_confidence?: number | null;
    first_seen?: string | null;
    last_seen?: string | null;
    span_days?: number | null;
    brands: CampaignCount[];
    advertisers: CampaignCount[];
    categories: CampaignCount[];
    subcategories: CampaignCount[];
  };
  messaging: {
    top_products: CampaignCount[];
    top_offers: CampaignCount[];
    top_ctas: CampaignCount[];
    top_prices: CampaignCount[];
    campaign_signals: CampaignCount[];
  };
  creative: {
    aspect_ratios: CampaignCount[];
    formats: CampaignCount[];
    voiceover_ads: number;
    on_screen_text_ads: number;
    disclaimer_ads: number;
    small_print_ads: number;
    disclaimer_density: CampaignCount[];
  };
  watchouts: {
    risk_labels: CampaignCount[];
    disclaimer_count: number;
    small_print_count: number;
    low_confidence_ads: string[];
  };
  insights: CampaignInsight[];
  research_prompts: string[];
};

export type CampaignDetail = {
  campaign: Campaign;
  ads: CampaignAd[];
  research: CampaignResearch;
};

export type CampaignDeepFinding = {
  priority: "high" | "medium" | "low" | string;
  title: string;
  detail: string;
  evidence_ad_ids: string[];
};

export type CampaignCreativeReviewItem = {
  area: "Attention" | "Branding" | "Connection" | "Direction" | string;
  status: string;
  detail: string;
};

export type CampaignAssignmentReview = {
  outliers: Array<{ ad_id?: string | null; reasons: string[] }>;
  missing_offer_ads: Array<string | null>;
  missing_cta_ads: Array<string | null>;
  missing_product_ads: Array<string | null>;
};

export type CampaignSuggestedEdit = {
  field: string;
  value: string;
  reason: string;
};

export type CampaignDeepResearch = {
  mode: "local" | string;
  include_web: boolean;
  web_available: boolean;
  requested_web?: boolean;
  requested_question?: string | null;
  analysis_mode?: string;
  research_source?: "llm" | "local" | string;
  scope: string;
  campaign: Campaign;
  generated_from: {
    ad_count: number;
    ad_ids: string[];
    evidence_tables: string[];
  };
  findings: CampaignDeepFinding[];
  creative_review: CampaignCreativeReviewItem[];
  assignment_review: CampaignAssignmentReview;
  suggested_edits: CampaignSuggestedEdit[];
  question_answer?: {
    question: string;
    answer: string;
    evidence_ad_ids: string[];
    limits: string;
    source?: "llm" | "local" | "local_fallback" | string;
    finish_reason?: string | null;
    error?: string;
  } | null;
  open_questions: string[];
  future_expansion: {
    web_research: string;
    supported_later: string[];
  };
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
  differences?: FieldDifference[];
};

export type TranscriptSegment = {
  id?: number;
  ad_id?: string;
  start_ms: number;
  end_ms: number;
  text: string;
  confidence?: number | null;
};

export type OcrItemDetail = {
  id?: number;
  ad_id?: string;
  frame_index: number;
  time_ms: number;
  frame_path?: string | null;
  engine: string;
  text: string;
  bbox?: number[] | null;
  confidence?: number | null;
};

export type StatsCount = {
  value?: string | null;
  count: number;
};

export type StatsResponse = {
  total_ads: number;
  by_status: StatsCount[];
  by_category: StatsCount[];
  by_brand: StatsCount[];
  risk_labels: StatsCount[];
};

export type CreativePanelPersona = {
  id: string;
  label: string;
  lens: string;
};

export type PanelCitation = {
  ad_id: string;
  time_ms?: number | null;
  frame_index?: number | null;
  source: string;
  text: string;
};

export type PersonaReaction = {
  persona_id: string;
  persona_label: string;
  lens: string;
  first_impression: string;
  understood_product_or_offer: string;
  emotional_reaction: string;
  trust_points: string[];
  confusion_points: string[];
  likely_objection: string;
  memorable_moment: string;
  cta_likelihood: string;
  citations: PanelCitation[];
};

export type ModeratorSummary = {
  consensus: string[];
  disagreements: string[];
  message_clarity_issues: string[];
  strongest_hooks: string[];
  suggested_ab_variants: string[];
};

export type DebateTurn = {
  round_index: number;
  phase: "opening" | "challenge" | "rebuttal" | "closing" | string;
  speaker_persona_id: string;
  speaker_label: string;
  stance: "advocate" | "skeptic" | "moderator" | "explorer" | string;
  target_persona_id?: string | null;
  claim: string;
  evidence_read: string;
  pressure_test: string;
  citations: PanelCitation[];
};

export type DebateTension = {
  axis: string;
  advocate: string;
  skeptic: string;
  moderator_take: string;
};

export type DebateScorecard = {
  moderator_verdict: string;
  strongest_argument: string;
  weakest_argument: string;
  unresolved_questions: string[];
  recommended_tests: string[];
};

export type CreativePanelReport = {
  ad_id: string;
  generated_at: string;
  json_path: string;
  report_type: string;
  analysis_source: "vlm" | "vlm_with_fallback" | "deterministic_fallback" | string;
  source_model?: string | null;
  fallback_error?: string | null;
  caveat: string;
  personas: PersonaReaction[];
  moderator_summary: ModeratorSummary;
  evidence_sources: string[];
};

export type CreativeDebateReport = {
  ad_id: string;
  generated_at: string;
  json_path: string;
  report_type: string;
  analysis_source: "vlm" | "vlm_with_fallback" | "deterministic_fallback" | string;
  source_model?: string | null;
  fallback_error?: string | null;
  topic: string;
  caveat: string;
  participants: PersonaReaction[];
  opening_statements: DebateTurn[];
  cross_examination: DebateTurn[];
  closing_statements: DebateTurn[];
  tensions: DebateTension[];
  scorecard: DebateScorecard;
  moderator_summary: ModeratorSummary;
  evidence_sources: string[];
};

export type FieldDifference = {
  field: string;
  left?: string | string[] | null;
  right?: string | string[] | null;
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
  rerank_score?: number | null;
  rerank_reason?: string | null;
  fts_rank?: number | null;
  vec_rank?: number | null;
  vec_distance?: number | null;
  source?: string | null;
  matched_frames?: Array<{
    frame_index?: number | null;
    time_ms?: number | null;
    path?: string | null;
    distance?: number | null;
  }>;
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
