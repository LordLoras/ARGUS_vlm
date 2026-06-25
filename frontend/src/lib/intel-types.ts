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
