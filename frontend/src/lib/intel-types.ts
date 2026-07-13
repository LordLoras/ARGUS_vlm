// Types for the intelligence crawler ("Watcher") surface. Kept separate from the
// large shared types.ts to stay isolated.

export type IntelTier = "A" | "B" | "C";
export type IntelPollOutcome = "success" | "partial" | "not_modified" | "explicit_empty" | "failed";

export type IntelPollDiagnostic = {
  code: string;
  category: string;
  message: string;
  retryable: boolean;
  provider?: string | null;
  phase?: string | null;
  http_status?: number | null;
  details: Record<string, unknown>;
};

export type IntelSource = {
  id: string;
  brand_name: string;
  market: string;
  source_type: string;
  tier: IntelTier;
  url?: string | null;
  platform?: string | null;
  platform_id?: string | null;
  enabled: boolean;
  poll_interval_hours: number;
  source_activated_at?: string | null;
  allowed_domains: string[];
  config: Record<string, unknown>;
  notes?: string | null;
};

export type IntelEvidence = {
  id: string;
  signal_id: string;
  resource_id?: string | null;
  source_id?: string | null;
  evidence_type: string;
  url?: string | null;
  text?: string | null;
  published_at?: string | null;
  confidence: number;
};

export type IntelSignal = {
  id: string;
  brand_name: string;
  campaign_group_id?: string | null;
  signal_type: string;
  status: string;
  confidence: number;
  title: string;
  summary?: string | null;
  campaign_name?: string | null;
  products: string[];
  first_seen_at: string;
  source_published_at?: string | null;
  last_seen_at: string;
  score_breakdown: Record<string, unknown>;
  evidence: IntelEvidence[];
};

export type IntelArtifactSummary = {
  screenshot_count: number;
  image_source_count: number;
  video_source_count: number;
  video_poster_count: number;
  background_image_source_count: number;
  link_count: number;
  media_asset_count: number;
};

export type IntelResourceArtifact = {
  artifact_type: string;
  label: string;
  url?: string | null;
  path?: string | null;
  text?: string | null;
};

export type IntelImpressionRange = {
  lower_bound?: number | null;
  upper_bound?: number | null;
};

export type IntelDeliverySurface = {
  surface_code?: string | null;
  surface_name?: string | null;
  impressions?: IntelImpressionRange | null;
};

export type IntelDeliveryRegion = {
  region_code?: string | null;
  region_name?: string | null;
  first_shown_at?: string | null;
  last_shown_at?: string | null;
  impressions?: IntelImpressionRange | null;
  surfaces: IntelDeliverySurface[];
};

export type IntelDeliverySummary = {
  regions: IntelDeliveryRegion[];
};

export type IntelCollectionContext = {
  requested_region_code?: string | null;
  collector_region_code?: string | null;
  collector_id?: string | null;
  source_url?: string | null;
};

export type IntelTargetingSummary = {
  raw: Record<string, unknown>;
  decoded: Record<string, unknown>;
};

export type IntelNormalizedAdvertiser = {
  id?: string | null;
  name?: string | null;
  url?: string | null;
};

export type IntelCreativeAsset = {
  asset_type: string;
  role: string;
  url?: string | null;
  path?: string | null;
  text?: string | null;
  source?: string | null;
};

export type IntelCreativeVariant = {
  id?: string | null;
  label?: string | null;
  description?: string | null;
  cta?: string | null;
  landing_url?: string | null;
  assets: IntelCreativeAsset[];
};

export type IntelNormalizedCreative = {
  id?: string | null;
  library_url?: string | null;
  format?: string | null;
  status?: string | null;
  title?: string | null;
  description?: string | null;
  first_shown_at?: string | null;
  last_shown_at?: string | null;
  served_days?: number | null;
  variant_count?: number | null;
  has_variants: boolean;
};

export type IntelNormalizedResource = {
  provider: string;
  adapter: string;
  platform?: string | null;
  source_url?: string | null;
  fetched_at: string;
  advertiser: IntelNormalizedAdvertiser;
  creative: IntelNormalizedCreative;
  variants: IntelCreativeVariant[];
  delivery: IntelDeliverySummary;
  targeting: IntelTargetingSummary;
  collection: IntelCollectionContext;
};

export type IntelResource = {
  id: string;
  brand_name: string;
  source_id: string;
  source_type: string;
  resource_type: string;
  url?: string | null;
  platform?: string | null;
  platform_id?: string | null;
  title?: string | null;
  description?: string | null;
  published_at?: string | null;
  first_seen_at: string;
  last_seen_at?: string | null;
  fetched_at: string;
  is_backfill: boolean;
  variant_count?: number | null;
  has_variants?: boolean;
  thumbnail_url?: string | null;
  duration_ms?: number | null;
  artifact_summary: IntelArtifactSummary;
  artifacts: IntelResourceArtifact[];
  normalized?: IntelNormalizedResource | null;
  metadata: Record<string, unknown>;
};

export type IntelBrandOverview = {
  brand_name: string;
  source_count: number;
  enabled_source_count: number;
  resource_count: number;
  backfill_resource_count: number;
  signal_count: number;
  latest_resource_seen_at?: string | null;
  latest_signal_seen_at?: string | null;
  source_types: string[];
  artifact_summary: IntelArtifactSummary;
};

export type IntelAdapterDescriptor = {
  source_type: string;
  label: string;
  target_label: string;
  target_placeholder: string;
  helper_text: string;
  default_tier: IntelTier;
  platform?: string | null;
  requires_url: boolean;
  requires_platform_id: boolean;
  config: Record<string, unknown>;
  provides: string[];
};

export type IntelDigestEntry = {
  brand_name: string;
  campaign_group_id?: string | null;
  headline: string;
  signal_count: number;
  top_confidence: number;
  signal_ids: string[];
  evidence_urls: string[];
};

export type IntelSourceRunItem = {
  source_id: string;
  status: "running" | "polled" | "partial" | "skipped" | "failed";
  new_resources: number;
  new_signals: number;
  backfilled: number;
  filtered: number;
  refreshed: number;
  baseline: boolean;
  reason?: string | null;
  outcome?: IntelPollOutcome | null;
  complete: boolean;
  truncated: boolean;
  truncation_reason?: string | null;
  failure_category?: string | null;
  error_code?: string | null;
  diagnostics: IntelPollDiagnostic[];
  next_due_at?: string | null;
  scan_mode?: "full" | "incremental" | "resume" | null;
  resumed: boolean;
  checkpoint_page?: number | null;
  stop_reason?: string | null;
};

export type IntelSourceState = {
  source_id: string;
  last_attempt_at?: string | null;
  last_success_at?: string | null;
  next_due_at?: string | null;
  last_error?: string | null;
  consecutive_errors: number;
  etag?: string | null;
  last_modified?: string | null;
  watermark?: string | null;
  lease_until?: string | null;
  lease_owner?: string | null;
  last_outcome?: IntelPollOutcome | null;
  last_error_category?: string | null;
  last_error_code?: string | null;
  cooldown_until?: string | null;
  last_diagnostics: IntelPollDiagnostic[];
};

export type IntelSourceStatus = {
  source: IntelSource;
  state: IntelSourceState;
  recent_runs: Array<
    IntelSourceRunItem & {
      run_id: string;
      started_at: string;
      finished_at?: string | null;
      error?: string | null;
      request_count: number;
      page_count: number;
      provider_item_count?: number | null;
    }
  >;
  provider_circuit?: {
    provider: string;
    open_until: string;
    source_id: string;
    error_code: string;
    category: string;
    message?: string | null;
  } | null;
  resume_available: boolean;
  resume_page?: number | null;
};

export type IntelCrawlSummary = {
  run_id: string;
  status: string;
  source_count: number;
  resource_count: number;
  signal_count: number;
  items: IntelSourceRunItem[];
  error?: string | null;
};

export type IntelCrawlRun = Omit<IntelCrawlSummary, "items"> & {
  sources: IntelSourceRunItem[];
  request?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  started_at?: string | null;
  finished_at?: string | null;
  attempt_count?: number;
};

export type IntelServiceHealth = {
  service_name: "worker" | "scheduler";
  status: "online" | "stale" | "not_started" | "stopped" | "error";
  activity: string;
  instance_id?: string | null;
  started_at?: string | null;
  heartbeat_at?: string | null;
  metadata: Record<string, unknown>;
};

export type IntelHealth = {
  schema_version: string;
  status: "healthy" | "degraded" | "critical";
  checked_at: string;
  queue: {
    queued: number;
    running: number;
    completed: number;
    degraded: number;
    failed: number;
    oldest_queued_at?: string | null;
    abandoned_running: number;
  };
  sources: {
    total: number;
    enabled: number;
    due: number;
    failed: number;
    partial: number;
    open_provider_circuits: number;
    resume_available: number;
  };
  services: IntelServiceHealth[];
  issues: Array<{
    code: string;
    severity: "warning" | "critical";
    message: string;
    source_id?: string;
    provider?: string;
  }>;
};

export type IntelSourceCreate = {
  id?: string;
  brand: string;
  source_type: string;
  tier?: IntelTier;
  url?: string | null;
  platform?: string | null;
  platform_id?: string | null;
  enabled?: boolean;
  poll_interval_hours?: number;
  config?: Record<string, unknown>;
};
