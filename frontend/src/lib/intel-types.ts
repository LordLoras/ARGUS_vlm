// Types for the intelligence crawler ("Watcher") surface. Kept separate from the
// large shared types.ts to stay isolated.

export type IntelTier = "A" | "B" | "C";

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

export type IntelResource = {
  id: string;
  brand_name: string;
  source_id: string;
  source_type: string;
  resource_type: string;
  url?: string | null;
  platform_id?: string | null;
  title?: string | null;
  description?: string | null;
  published_at?: string | null;
  first_seen_at: string;
  fetched_at: string;
  is_backfill: boolean;
  variant_count?: number | null;
  has_variants?: boolean;
  artifact_summary: IntelArtifactSummary;
  artifacts: IntelResourceArtifact[];
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
  status: "polled" | "skipped" | "failed";
  new_resources: number;
  new_signals: number;
  backfilled: number;
  baseline: boolean;
  reason?: string | null;
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
