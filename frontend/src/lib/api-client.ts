import { fetchEventSource } from "@microsoft/fetch-event-source";

import type {
  AdDetail,
  AdRecord,
  AgentMessage,
  AgentSession,
  AgentStreamEvent,
  BrandProfileEnrichmentResponse,
  BrandProfileCandidate,
  Campaign,
  CampaignDeepResearch,
  CampaignDetail,
  CreativeDebateReport,
  CreativePanelPersona,
  CreativePanelReport,
  EntityGraphPayload,
  EntityNode,
  EntityTaxonomyMappingSummary,
  CrawlerResult,
  CrawlerRunRecord,
  CrawlerTraceItem,
  AdChangeSuggestion,
  IngestAssistMode,
  IngestAssistResult,
  FrameRecord,
  JobStreamEvent,
  JobRecord,
  OcrItemDetail,
  ProductPage,
  ProductEntityUpdatePayload,
  ProductSummary,
  RelatedAds,
  ResolverResult,
  SearchHit,
  SettingsConfig,
  SettingsSnapshot,
  StatsResponse,
  SubmittedAdCrawlQueueItem,
  TranscriptSegment
} from "./types";
import type {
  IntelAdapterDescriptor,
  IntelBrandOverview,
  IntelCrawlSummary,
  IntelDigestEntry,
  IntelResource,
  IntelSignal,
  IntelSource,
  IntelSourceCreate
} from "./intel-types";

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers
    },
    ...init
  });
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, text || response.statusText);
  }
  return (await response.json()) as T;
}

function params(values: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  health: () => apiFetch<{ status: string; service: string }>("/api/health"),

  getSettings: () => apiFetch<SettingsSnapshot>("/api/settings"),

  updateSettings: (config: SettingsConfig) =>
    apiFetch<SettingsSnapshot>("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ config })
    }),

  addApiKey: (body: { name: string; value: string }) =>
    apiFetch<SettingsSnapshot>("/api/settings/api-keys", {
      method: "POST",
      body: JSON.stringify(body)
    }),

  deleteApiKey: (name: string) =>
    apiFetch<SettingsSnapshot>(`/api/settings/api-keys/${encodeURIComponent(name)}`, {
      method: "DELETE"
    }),

  listAds: (query: { brand?: string; promotion?: string; category?: string; risk_label?: string; iab_unique_id?: string; iab_tier_1?: string; iab_content_id?: string; status?: string; q?: string; limit?: number; offset?: number }) =>
    apiFetch<{ items: AdRecord[]; limit: number; offset: number }>(`/api/ads${params(query)}`),

  getAd: (adId: string) => apiFetch<AdDetail>(`/api/ads/${adId}`),

  enrichBrandProfile: (
    adId: string,
    body: {
      target: "brand" | "advertiser";
      force?: boolean;
      query?: string | null;
      wikipedia_title?: string | null;
      wikidata_qid?: string | null;
    }
  ) =>
    apiFetch<BrandProfileEnrichmentResponse>(`/api/ads/${adId}/brand-profile/enrich`, {
      method: "POST",
      body: JSON.stringify(body)
    }),

  searchBrandProfiles: (
    adId: string,
    query: { target: "brand" | "advertiser"; q?: string | null }
  ) =>
    apiFetch<{ target: "brand" | "advertiser"; query: string; items: BrandProfileCandidate[] }>(
      `/api/ads/${adId}/brand-profile/search${params(query)}`
    ),

  resetBrandProfile: (adId: string, target: "brand" | "advertiser") =>
    apiFetch<{ target: "brand" | "advertiser"; deleted: boolean }>(
      `/api/ads/${adId}/brand-profile/${target}`,
      { method: "DELETE" }
    ),

  getFrames: (adId: string) =>
    apiFetch<{ items: FrameRecord[] }>(`/api/ads/${adId}/frames`),

  getTranscript: (adId: string) =>
    apiFetch<{ ad_id: string; items: TranscriptSegment[]; full_text: string }>(
      `/api/ads/${adId}/transcript`
    ),

  getOcr: (adId: string) =>
    apiFetch<{ ad_id: string; items: OcrItemDetail[] }>(`/api/ads/${adId}/ocr`),

  getEvidence: (adId: string) =>
    apiFetch<{ classification_evidence: unknown[]; rule_triggers: unknown[] }>(
      `/api/ads/${adId}/evidence`
    ),

  getSimilar: (adId: string, k = 10) =>
    apiFetch<RelatedAds>(`/api/ads/${adId}/similar${params({ k })}`),

  getEvidenceExport: (adId: string) =>
    apiFetch<Record<string, unknown>>(`/api/ads/${adId}/export/evidence`),

  getStats: (query: { brand?: string; category?: string; status?: string; limit?: number } = {}) =>
    apiFetch<StatsResponse>(`/api/stats${params(query)}`),

  listCreativePanelPersonas: () =>
    apiFetch<{ items: CreativePanelPersona[] }>("/api/creative-panel/personas"),

  createCreativePanel: (
    adId: string,
    personaIds?: string[],
    useVlm = true,
    enableReasoning = true
  ) =>
    apiFetch<CreativePanelReport>(`/api/ads/${adId}/creative-panel`, {
      method: "POST",
      body: JSON.stringify({
        persona_ids: personaIds,
        use_vlm: useVlm,
        enable_reasoning: enableReasoning
      })
    }),

  createCreativeDebate: (
    adId: string,
    body: {
      personaIds?: string[];
      topic?: string;
      useVlm?: boolean;
      enableReasoning?: boolean;
    } = {}
  ) =>
    apiFetch<CreativeDebateReport>(`/api/ads/${adId}/creative-panel/debate`, {
      method: "POST",
      body: JSON.stringify({
        persona_ids: body.personaIds,
        topic: body.topic,
        use_vlm: body.useVlm ?? true,
        enable_reasoning: body.enableReasoning ?? true
      })
    }),

  patchAd: (
    adId: string,
    patch: {
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
      iab_product_id?: string | null;
      iab_content_ids?: string[] | null;
      tagline?: string | null;
      offers?: Array<{ text: string }> | null;
      ctas?: Array<{ text: string }> | null;
    }
  ) =>
    apiFetch<AdRecord>(`/api/ads/${adId}`, {
      method: "PATCH",
      body: JSON.stringify(patch)
    }),

  deleteAd: (adId: string, cleanupArtifacts = false) =>
    apiFetch<{ deleted: string; artifacts_removed: string[] }>(
      `/api/ads/${adId}${params({ cleanup_artifacts: cleanupArtifacts })}`,
      { method: "DELETE" }
    ),

  uploadAd: (file: File, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("file", file);
    return apiFetch<{ ad_id: string; job_id: string | null; state: string; duplicate_of?: string }>(
      "/api/ads/upload",
      { method: "POST", body: form, signal }
    );
  },

  getJob: (jobId: string) => apiFetch<JobRecord>(`/api/jobs/${jobId}`),

  listJobs: (query: { state?: string; limit?: number; offset?: number } = {}) =>
    apiFetch<{ items: JobRecord[]; limit: number; offset: number }>(`/api/jobs${params(query)}`),

  cancelJob: (jobId: string) =>
    apiFetch<{ cancelled: boolean; job: JobRecord }>(`/api/jobs/${jobId}/cancel`, {
      method: "POST"
    }),

  deleteJob: (jobId: string, cleanupArtifacts = true) =>
    apiFetch<{ deleted: string; ad_id?: string | null; artifacts_removed: string[] }>(
      `/api/jobs/${jobId}${params({ cleanup_artifacts: cleanupArtifacts })}`,
      { method: "DELETE" }
    ),

  search: (query: {
    q?: string;
    mode?: string;
    ad_id?: string;
    brand?: string;
    promotion?: string;
    category?: string;
    risk_label?: string;
    status?: string;
    rerank?: boolean;
    k?: number;
  }) =>
    apiFetch<{ mode: string; strategy?: string; filtered_count?: number; items: SearchHit[] }>(
      `/api/search${params(query)}`
    ),

  getEmbeddingsScatter: (type: "text" | "visual", sample = 600, layout?: "guided" | "real") =>
    apiFetch<{
      points: Array<{
        id: string;
        x: number;
        y: number;
        z: number;
        category: string;
        confidence: number;
        brand: string;
        label: string;
      }>;
      categories: string[];
      total: number;
      sampled: number;
      type: string;
      projection?: string;
    }>(`/api/embeddings/scatter${params({ type, sample, layout: layout || undefined })}`),

  listCampaigns: (query: { brand?: string; created_by?: string; q?: string; limit?: number; offset?: number } = {}) =>
    apiFetch<{ items: Campaign[]; limit: number; offset: number }>(`/api/campaigns${params(query)}`),

  createCampaign: (body: Partial<Campaign> & { name: string }) =>
    apiFetch<Campaign>("/api/campaigns", { method: "POST", body: JSON.stringify(body) }),

  getCampaign: (campaignId: string) =>
    apiFetch<CampaignDetail>(`/api/campaigns/${encodeURIComponent(campaignId)}`),

  updateCampaign: (campaignId: string, body: Partial<Campaign>) =>
    apiFetch<Campaign>(`/api/campaigns/${encodeURIComponent(campaignId)}`, {
      method: "PATCH",
      body: JSON.stringify(body)
    }),

  deleteCampaign: (campaignId: string) =>
    apiFetch<{ deleted: string }>(`/api/campaigns/${encodeURIComponent(campaignId)}`, {
      method: "DELETE"
    }),

  runCampaignDeepResearch: (
    campaignId: string,
    body: {
      include_web?: boolean;
      depth?: "standard" | "deep";
      question?: string;
      thinking?: boolean;
    } = {}
  ) =>
    apiFetch<CampaignDeepResearch>(
      `/api/campaigns/${encodeURIComponent(campaignId)}/research/deep`,
      {
        method: "POST",
        body: JSON.stringify({ include_web: false, depth: "deep", ...body })
      }
    ),

  discoverCampaigns: () =>
    apiFetch<{ campaigns?: Campaign[]; discovered?: unknown[]; proposals?: unknown[] }>("/api/campaigns/discover", {
      method: "POST"
    }),

  acceptCampaignProposals: (body: { campaign_ids?: string[]; proposals?: unknown[] }) =>
    apiFetch<{ accepted: Campaign[] }>("/api/campaigns/discover/accept", {
      method: "POST",
      body: JSON.stringify(body)
    }),

  assignAdsToCampaign: (campaignId: string, adIds: string[]) =>
    apiFetch<{ campaign_id: string; assigned: string[] }>(`/api/campaigns/${encodeURIComponent(campaignId)}/ads`, {
      method: "POST",
      body: JSON.stringify({ ad_ids: adIds })
    }),

  unassignAdFromCampaign: (campaignId: string, adId: string) =>
    apiFetch<{ campaign_id: string; unassigned: string }>(
      `/api/campaigns/${encodeURIComponent(campaignId)}/ads/${encodeURIComponent(adId)}`,
      { method: "DELETE" }
    ),

  listAgentSessions: () =>
    apiFetch<{ items: AgentSession[]; limit: number; offset: number }>("/api/agent/sessions"),

  createAgentSession: () =>
    apiFetch<{ session_id: string }>("/api/agent/sessions", { method: "POST" }),

  getAgentSession: (sessionId: string) =>
    apiFetch<{ session: AgentSession; messages: AgentMessage[] }>(`/api/agent/sessions/${sessionId}`),

  deleteAgentSession: (sessionId: string) =>
    apiFetch<{ deleted: string }>(`/api/agent/sessions/${sessionId}`, { method: "DELETE" }),

  listAgentTools: () =>
    apiFetch<{ tools: Array<{ name: string; description: string; parameters: unknown }> }>(
      "/api/agent/tools"
    ),

  listEntityProducts: (query: { status?: string; q?: string; limit?: number; offset?: number } = {}) =>
    apiFetch<{ items: ProductSummary[]; limit: number; offset: number }>(
      `/api/entity-graph/products${params(query)}`
    ),

  getEntityProduct: (productId: string) =>
    apiFetch<ProductPage>(`/api/entity-graph/products/${encodeURIComponent(productId)}`),

  getEntityProductCrawlerTrace: (productId: string, limit = 50) =>
    apiFetch<{ items: CrawlerTraceItem[]; limit: number }>(
      `/api/entity-graph/products/${encodeURIComponent(productId)}/crawler-trace${params({ limit })}`
    ),

  updateEntityProduct: (productId: string, body: ProductEntityUpdatePayload) =>
    apiFetch<ProductPage>(`/api/entity-graph/products/${encodeURIComponent(productId)}`, {
      method: "PATCH",
      body: JSON.stringify(body)
    }),

  lookupEntityNodes: (query: { entity_type: string; q?: string; limit?: number }) =>
    apiFetch<{ items: EntityNode[]; limit: number }>(
      `/api/entity-graph/nodes/lookup${params(query)}`
    ),

  getEntityGraph: (limit = 400) =>
    apiFetch<EntityGraphPayload>(`/api/entity-graph/graph${params({ limit })}`),

  getEntityTaxonomyMappings: (limit = 200) =>
    apiFetch<{ items: EntityTaxonomyMappingSummary[]; limit: number }>(
      `/api/entity-graph/taxonomy-mappings${params({ limit })}`
    ),

  getEntityReadonlyStatus: () =>
    apiFetch<{ submitted_db_query_only: boolean }>("/api/entity-graph/readonly-status"),

  previewEntityResolver: (body: { mode?: string; fully_automatic?: boolean; limit?: number } = {}) =>
    apiFetch<ResolverResult>("/api/entity-graph/resolver/preview", {
      method: "POST",
      body: JSON.stringify(body)
    }),

  runEntityResolver: (body: { mode?: string; fully_automatic?: boolean; limit?: number } = {}) =>
    apiFetch<ResolverResult>("/api/entity-graph/resolver/run", {
      method: "POST",
      body: JSON.stringify(body)
    }),

  runEntityCrawler: (body: {
    limit?: number;
    ad_ids?: string[];
    targets?: Array<{ ad_id: string; url: string }>;
    rerun_mode?: "skip_crawled" | "rerun_crawled" | "refresh";
  } = {}) =>
    apiFetch<CrawlerResult>("/api/entity-graph/crawler/run", {
      method: "POST",
      body: JSON.stringify(body)
    }),

  startEntityCrawlerRun: (body: {
    limit?: number;
    ad_ids?: string[];
    targets?: Array<{ ad_id: string; url: string }>;
    rerun_mode?: "skip_crawled" | "rerun_crawled" | "refresh";
  } = {}) =>
    apiFetch<CrawlerRunRecord>("/api/entity-graph/crawler/runs", {
      method: "POST",
      body: JSON.stringify(body)
    }),

  getEntityCrawlerRun: (runId: string) =>
    apiFetch<CrawlerRunRecord>(`/api/entity-graph/crawler/runs/${encodeURIComponent(runId)}`),

  listEntityCrawlerRuns: (limit = 20) =>
    apiFetch<{ items: CrawlerRunRecord[]; limit: number }>(
      `/api/entity-graph/crawler/runs${params({ limit })}`
    ),

  listEntityCrawlerQueue: (query: { q?: string; limit?: number } = {}) =>
    apiFetch<{ items: SubmittedAdCrawlQueueItem[]; limit: number }>(
      `/api/entity-graph/crawler/queue${params(query)}`
    ),

  listAdChangeSuggestions: (args: { status?: string; ad_id?: string; limit?: number } = {}) =>
    apiFetch<{ items: AdChangeSuggestion[]; limit: number }>(
      `/api/entity-graph/ad-change-suggestions${params(args)}`
    ),

  approveAdChangeSuggestion: (suggestionId: string) =>
    apiFetch<AdChangeSuggestion>(
      `/api/entity-graph/ad-change-suggestions/${encodeURIComponent(suggestionId)}/approve`,
      { method: "POST" }
    ),

  rejectAdChangeSuggestion: (suggestionId: string) =>
    apiFetch<AdChangeSuggestion>(
      `/api/entity-graph/ad-change-suggestions/${encodeURIComponent(suggestionId)}/reject`,
      { method: "POST" }
    ),

  applyAdChangeSuggestion: (suggestionId: string, value?: string) =>
    apiFetch<AdChangeSuggestion>(
      `/api/entity-graph/ad-change-suggestions/${encodeURIComponent(suggestionId)}/apply`,
      {
        method: "POST",
        body: JSON.stringify({ value: value || undefined })
      }
    ),

  promoteEntity: (entityId: string) =>
    apiFetch<EntityNode>(`/api/entity-graph/entities/${encodeURIComponent(entityId)}/promote`, {
      method: "POST"
    }),

  rejectEntity: (entityId: string) =>
    apiFetch<EntityNode>(`/api/entity-graph/entities/${encodeURIComponent(entityId)}/reject`, {
      method: "POST"
    }),

  reviewEntity: (entityId: string, status: string) =>
    apiFetch<EntityNode>(`/api/entity-graph/entities/${encodeURIComponent(entityId)}/review`, {
      method: "POST",
      body: JSON.stringify({ status })
    }),

  addDiscoveryCandidate: (body: {
    entity_type?: string;
    name: string;
    aliases?: string[];
    source_url?: string | null;
    notes?: string | null;
    confidence?: number;
  }) =>
    apiFetch<EntityNode>("/api/entity-graph/discovery-candidates", {
      method: "POST",
      body: JSON.stringify(body)
    }),

  previewIngestAssist: (body: {
    mode?: IngestAssistMode;
    products?: string[];
    brand_name?: string | null;
    category_name?: string | null;
  }) =>
    apiFetch<IngestAssistResult>("/api/entity-graph/ingest-assist/preview", {
      method: "POST",
      body: JSON.stringify(body)
    }),

  listIntelSources: (query: { brand?: string; enabled_only?: boolean } = {}) =>
    apiFetch<{ items: IntelSource[] }>(`/api/intelligence/sources${params(query)}`),

  listIntelAdapters: () =>
    apiFetch<{ items: IntelAdapterDescriptor[] }>("/api/intelligence/adapters"),

  listIntelBrands: (query: { q?: string; limit?: number } = {}) =>
    apiFetch<{ items: IntelBrandOverview[]; limit: number }>(
      `/api/intelligence/brands${params(query)}`
    ),

  listIntelResources: (
    query: {
      brand?: string;
      source_id?: string;
      include_backfill?: boolean;
      limit?: number;
    } = {}
  ) =>
    apiFetch<{ items: IntelResource[]; limit: number }>(
      `/api/intelligence/resources${params(query)}`
    ),

  createIntelSource: (body: IntelSourceCreate) =>
    apiFetch<IntelSource>("/api/intelligence/sources", {
      method: "POST",
      body: JSON.stringify(body)
    }),

  updateIntelSource: (
    sourceId: string,
    body: Partial<IntelSourceCreate> & { enabled?: boolean }
  ) =>
    apiFetch<IntelSource>(`/api/intelligence/sources/${encodeURIComponent(sourceId)}`, {
      method: "PATCH",
      body: JSON.stringify(body)
    }),

  deleteIntelSource: (sourceId: string) =>
    apiFetch<{ deleted: string }>(`/api/intelligence/sources/${encodeURIComponent(sourceId)}`, {
      method: "DELETE"
    }),

  crawlIntelSource: (sourceId: string) =>
    apiFetch<IntelCrawlSummary>(
      `/api/intelligence/sources/${encodeURIComponent(sourceId)}/crawl`,
      { method: "POST" }
    ),

  runIntelCrawl: (body: { due?: boolean; source_id?: string; brand?: string } = {}) =>
    apiFetch<IntelCrawlSummary>("/api/intelligence/crawl", {
      method: "POST",
      body: JSON.stringify({ due: true, ...body })
    }),

  listIntelSignals: (
    query: { brand?: string; since?: string; status?: string; limit?: number } = {}
  ) =>
    apiFetch<{ items: IntelSignal[]; limit: number }>(`/api/intelligence/signals${params(query)}`),

  getIntelDigest: (since = "30d") =>
    apiFetch<{ entries: IntelDigestEntry[] }>(`/api/intelligence/digest${params({ since })}`),

  listIntelSourceTypes: () =>
    apiFetch<{ source_types: string[] }>("/api/intelligence/source-types")
};

export function streamJobEvents(jobId: string, onEvent: (event: JobStreamEvent) => void) {
  const controller = new AbortController();
  void fetchEventSource(`${API_BASE_URL}/api/jobs/${jobId}/events`, {
    signal: controller.signal,
    onmessage(message) {
      if (!message.data) return;
      const parsed = JSON.parse(message.data) as JobStreamEvent;
      onEvent(parsed);
    },
    onerror(error) {
      throw error;
    }
  });
  return () => controller.abort();
}

export function streamAgentQuery(
  sessionId: string,
  message: string,
  onEvent: (event: AgentStreamEvent) => void
) {
  const controller = new AbortController();
  const url = `${API_BASE_URL}/api/agent/sessions/${sessionId}/events?q=${encodeURIComponent(message)}`;
  
  let hasCompleted = false;
  
  void fetchEventSource(url, {
    method: "GET",
    signal: controller.signal,
    headers: { Accept: "text/event-stream" },
    openWhenHidden: true,
    onmessage(event) {
      if (!event.event || !event.data) return;
      try {
        const payload = JSON.parse(event.data) as Record<string, unknown>;
        onEvent({ type: event.event as AgentStreamEvent["type"], payload } as AgentStreamEvent);
        
        // Mark stream as complete when done event received
        if (event.event === "done") {
          hasCompleted = true;
        }
      } catch (err) {
        onEvent({
          type: "error",
          payload: {
            session_id: sessionId,
            message: err instanceof Error ? err.message : String(err)
          }
        });
      }
    },
    onerror(error) {
      // Only report error if we haven't already received a done event
      if (!hasCompleted) {
        onEvent({
          type: "error",
          payload: {
            session_id: sessionId,
            message: error instanceof Error ? error.message : String(error)
          }
        });
        // Ensure we send a done event so the UI knows streaming is complete
        onEvent({
          type: "done",
          payload: { session_id: sessionId }
        });
      }
      // Don't rethrow error - handle it gracefully
    }
  });
  
  return () => controller.abort();
}
