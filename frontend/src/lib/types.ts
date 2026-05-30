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
  promotion_name?: string | null;
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
  iab_content_ids?: string | null;
  iab_content_paths?: string | null;
  iab_content_categories_json?: string | null;
  source_hash?: string | null;
  phash_mean?: string | null;
  duplicate_of?: string | null;
  duplicate_verdict?: string | null;
  duplicate_score?: number | null;
  first_frame_path?: string | null;
};

export type EndpointSettings = {
  endpoint: string;
  model: string;
  api_key_env?: string | null;
  timeout_s: number;
  max_retries: number;
  retry_delay_s: number;
  temperature: number;
  max_tokens: number;
  enable_thinking?: boolean;
  response_format?: "json_object" | "json_schema" | string;
  stream: boolean;
};

export type SettingsConfig = {
  paths: Record<string, string>;
  ingest: {
    ffmpeg_path: string;
    ffprobe_path: string;
    frame_interval_ms: number;
    audio_sample_rate: number;
  };
  whisper?: Record<string, unknown>;
  dedup?: Record<string, unknown>;
  ocr: {
    enabled: boolean;
    backend: string;
    device: string;
    lang: string;
  };
  paddlevl?: Record<string, unknown>;
  glm_ocr: {
    enabled: boolean;
    mode: "local" | "remote" | string;
    prompt: string;
    image_max_dim: number;
    include_in_search: boolean;
    include_in_vlm_bundle: boolean;
    run_on_text_frames: boolean;
    min_ocr_chars: number;
    run_when_ocr_disabled: boolean;
    max_frames_per_ad: number;
    local: Omit<EndpointSettings, "enable_thinking" | "response_format">;
    remote: Omit<EndpointSettings, "enable_thinking" | "response_format">;
    gating?: Record<string, unknown>;
  };
  rules: {
    rules_path?: string | null;
    alignment_window_ms: number;
  };
  vlm: {
    mode: "local" | "remote" | "frontier" | string;
    prompt_profile: "auto" | "standard" | "frontier_strict" | string;
    max_frames_in_bundle: number;
    image_max_dim: number;
    enable_ocr_cleanup_pass: boolean;
    enable_self_correction: boolean;
    enable_post_validation: boolean;
    enable_visual_verify: boolean;
    complexity?: Record<string, unknown>;
    local: EndpointSettings;
    remote: EndpointSettings;
    frontier: EndpointSettings;
  };
  text_embedder: {
    model: string;
    device: string;
    batch_size: number;
    dim: number;
  };
  image_embedder: {
    enabled: boolean;
    model: string;
    device: string;
    batch_size: number;
    dim: number;
  };
  vector_store: {
    backend: string;
    text_dim: number;
    visual_dim: number;
  };
  campaigns?: Record<string, unknown>;
  api: {
    host: string;
    port: number;
    cors_origins: string[];
    upload: {
      max_bytes: number;
      allowed_mime: string[];
    };
  };
  worker: {
    poll_interval_ms: number;
    concurrency: number;
  };
  agent: {
    inherit_vlm: boolean;
    inherit_vlm_mode?: "active" | "local" | "remote" | "frontier" | string;
    endpoint: Partial<EndpointSettings>;
    max_iterations: number;
    list_max_rows: number;
    sql_readonly_max_rows: number;
    sql_statement_timeout_s: number;
    temperature: number;
    max_tokens: number;
  };
  creative_panel: {
    inherit_vlm: boolean;
    endpoint: Partial<EndpointSettings>;
    temperature: number;
    max_tokens: number;
  };
  search: Record<string, unknown>;
  brand_profiles: {
    enabled: boolean;
    user_agent: string;
    timeout_s: number;
    cache_days: number;
    max_candidates: number;
    max_parent_depth: number;
  };
};

export type ApiKeyRecord = {
  name: string;
  available: boolean;
  managed: boolean;
  sources: string[];
  used_by: string[];
  value: null;
  redacted: true;
};

export type SettingsSnapshot = {
  config_path: string;
  dotenv_path: string;
  config: SettingsConfig;
  api_keys: ApiKeyRecord[];
  options: {
    vlm_modes: Array<{ value: "local" | "remote" | "frontier" | string; label: string; description: string }>;
    prompt_profiles: Array<{ value: "auto" | "standard" | "frontier_strict" | string; label: string; description: string }>;
    response_formats: string[];
    glm_ocr_modes: string[];
    devices: string[];
  };
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

export type IABContentCategory = {
  iab_unique_id: string;
  iab_parent_id?: string | null;
  tier_1?: string | null;
  tier_2?: string | null;
  tier_3?: string | null;
  tier_4?: string | null;
  selected_depth: number;
  selected_category: string;
  full_path: string;
  confidence?: string | null;
  reason?: string | null;
  parent_categories?: Array<{
    iab_unique_id: string;
    name: string;
    depth: number;
    full_path: string;
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
  iab_content_categories?: IABContentCategory[];
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
  promotion_name?: string | null;
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
  advertiser?: {
    advertiser_name?: string | null;
    brand_name?: string | null;
    parent_company?: string | null;
    service_area?: string[];
    locations?: string[];
    evidence?: EvidenceItem[];
  };
};

export type BrandProfileLookupStep = {
  source: string;
  action: string;
  status?: string | null;
  query?: string | null;
  title?: string | null;
  qid?: string | null;
  url?: string | null;
  result_count?: number | null;
  detail?: string | null;
};

export type BrandProfile = {
  normalized_name: string;
  query_name: string;
  display_name?: string | null;
  description?: string | null;
  summary?: string | null;
  wikipedia_title?: string | null;
  wikipedia_url?: string | null;
  wikipedia_page_id?: number | null;
  wikidata_qid?: string | null;
  parent_companies?: string[];
  owners?: string[];
  corporate_chain?: string[];
  industries?: string[];
  official_website?: string | null;
  headquarters?: string[];
  countries?: string[];
  inception?: string | null;
  founded_by?: string[];
  subsidiaries?: string[];
  key_metrics?: Record<string, string | string[]>;
  lookup_steps?: BrandProfileLookupStep[];
  source_urls?: string[];
  source_json?: Record<string, unknown>;
  fetched_at?: string | null;
  expires_at?: string | null;
};

export type BrandProfileEnrichmentResponse = {
  target: "brand" | "advertiser";
  cached: boolean;
  profile: BrandProfile;
};

export type BrandProfileCandidate = {
  title: string;
  pageid?: number | null;
  snippet?: string | null;
  url?: string | null;
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

export type CampaignProductFamily = CampaignCount & {
  ad_count?: number | null;
  total_duration_ms?: number | null;
  ad_ids?: string[];
  variants?: CampaignCount[];
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
    product_families?: CampaignProductFamily[];
    top_offers: CampaignCount[];
    top_ctas: CampaignCount[];
    top_prices: CampaignCount[];
    campaign_signals: CampaignCount[];
  };
  creative: {
    runtime_buckets?: CampaignCount[];
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
  brand_profile?: BrandProfile | null;
  advertiser_profile?: BrandProfile | null;
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
  ad_id?: string | null;
  state: string;
  progress?: number | null;
  message?: string | null;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  ad_status?: string | null;
  source_path?: string | null;
  brand_name?: string | null;
  primary_category?: string | null;
  ingested_at?: string | null;
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
