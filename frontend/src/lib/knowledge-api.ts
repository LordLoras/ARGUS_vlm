import type { ApiError } from "./api-client";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function kbFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/api/knowledge${path}`, {
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...init?.headers,
    },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw Object.assign(new Error(text || response.statusText), { status: response.status });
  }
  return response.json() as Promise<T>;
}

function params(values: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

// ── Types ──────────────────────────────────────────────────

export interface IABEntry {
  unique_id: string;
  parent_id: string | null;
  name: string;
  tier_1: string | null;
  tier_2: string | null;
  tier_3: string | null;
  tier_4: string | null;
  active: boolean;
  selected_depth?: number;
  selected_category?: string;
  full_path?: string;
}

export interface BrandRule {
  id: number;
  brand_name: string;
  primary_category: string | null;
  iab_product_id: string | null;
  iab_content_ids: string[];
  subcategory: string | null;
  source: string;
  confidence: number;
  priority: number;
  active: boolean;
  notes: string | null;
}

export interface Override {
  id: number;
  override_type: string;
  pattern: string;
  primary_category: string | null;
  iab_product_id: string | null;
  iab_content_ids: string[];
  priority: number;
  active: boolean;
  notes: string | null;
}

export interface InferenceRule {
  id: number;
  taxonomy_type: string;
  target_id: string;
  terms: string[];
  context_terms: string[];
  priority: number;
  active: boolean;
  notes: string | null;
}

export interface KnowledgeStats {
  product_taxonomy: { total: number; active: number };
  content_taxonomy: { total: number; active: number };
  brand_rules: number;
  overrides: number;
  inference_rules: number;
  corrections_logged: number;
  versions: Array<{
    taxonomy_type: string;
    version: string;
    entries_count: number;
    loaded_at: string;
  }>;
}

export interface BackfillSuggestion {
  ad_id: string;
  brand_name: string | null;
  current_primary_category: string | null;
  suggested_primary_category: string | null;
  current_iab_product_id: string | null;
  suggested_iab_product_id: string | null;
  suggested_iab_content_ids: string[];
  rule_source: string | null;
  confidence: number;
}

// ── API ────────────────────────────────────────────────────

export const knowledgeApi = {
  stats: () => kbFetch<KnowledgeStats>("/stats"),

  loadTaxonomies: (body?: { product_tsv?: string; content_tsv?: string }) =>
    kbFetch<{ product_entries: number; content_entries: number; inference_rules: number }>(
      "/load-taxonomies",
      { method: "POST", body: JSON.stringify(body ?? {}) }
    ),

  // Product taxonomy
  listProduct: (opts?: { parent_id?: string; tier_1?: string; active_only?: boolean }) =>
    kbFetch<IABEntry[]>(`/taxonomy/product${params(opts as Record<string, unknown>)}`),
  getProduct: (id: string) => kbFetch<IABEntry>(`/taxonomy/product/${id}`),
  searchProduct: (q: string) => kbFetch<IABEntry[]>(`/taxonomy/product-search${params({ q })}`),
  toggleProduct: (id: string, active: boolean) =>
    kbFetch<{ unique_id: string; active: boolean }>(`/taxonomy/product/${id}/active?active=${active}`, {
      method: "PATCH",
    }),

  // Content taxonomy
  listContent: (opts?: { parent_id?: string; tier_1?: string; active_only?: boolean }) =>
    kbFetch<IABEntry[]>(`/taxonomy/content${params(opts as Record<string, unknown>)}`),
  getContent: (id: string) => kbFetch<IABEntry>(`/taxonomy/content/${id}`),
  searchContent: (q: string) => kbFetch<IABEntry[]>(`/taxonomy/content-search${params({ q })}`),
  toggleContent: (id: string, active: boolean) =>
    kbFetch<{ unique_id: string; active: boolean }>(`/taxonomy/content/${id}/active?active=${active}`, {
      method: "PATCH",
    }),

  // Brand rules
  listBrandRules: (activeOnly = true) =>
    kbFetch<BrandRule[]>(`/brand-rules${params({ active_only: activeOnly })}`),
  lookupBrandRule: (brand: string) =>
    kbFetch<BrandRule | null>(`/brand-rules/lookup${params({ brand })}`),
  createBrandRule: (rule: Partial<BrandRule>) =>
    kbFetch<BrandRule>("/brand-rules", { method: "POST", body: JSON.stringify(rule) }),
  deleteBrandRule: (id: number) =>
    kbFetch<{ deleted: boolean }>(`/brand-rules/${id}`, { method: "DELETE" }),

  // Overrides
  listOverrides: (type?: string) =>
    kbFetch<Override[]>(`/overrides${params({ override_type: type })}`),
  createOverride: (o: Partial<Override>) =>
    kbFetch<Override>("/overrides", { method: "POST", body: JSON.stringify(o) }),
  deleteOverride: (id: number) =>
    kbFetch<{ deleted: boolean }>(`/overrides/${id}`, { method: "DELETE" }),

  // Inference rules
  listInferenceRules: (type?: string) =>
    kbFetch<InferenceRule[]>(`/inference-rules${params({ taxonomy_type: type })}`),
  createInferenceRule: (r: Partial<InferenceRule>) =>
    kbFetch<InferenceRule>("/inference-rules", { method: "POST", body: JSON.stringify(r) }),
  deleteInferenceRule: (id: number) =>
    kbFetch<{ deleted: boolean }>(`/inference-rules/${id}`, { method: "DELETE" }),

  // Backfill
  analyzeBackfill: (brandRulesOnly = true, limit = 1000) =>
    kbFetch<BackfillSuggestion[]>(`/backfill/analyze${params({ brand_rules_only: brandRulesOnly, limit })}`, {
      method: "POST",
    }),
  applyBackfill: (s: BackfillSuggestion) =>
    kbFetch<{ applied: boolean; ad_id: string }>("/backfill/apply", {
      method: "POST",
      body: JSON.stringify(s),
    }),
};
