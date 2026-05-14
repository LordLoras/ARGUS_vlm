import { fetchEventSource } from "@microsoft/fetch-event-source";

import type {
  AdDetail,
  AdRecord,
  AgentMessage,
  AgentSession,
  AgentStreamEvent,
  Campaign,
  CampaignDeepResearch,
  CampaignDetail,
  FrameRecord,
  JobStreamEvent,
  JobRecord,
  RelatedAds,
  SearchHit
} from "./types";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
  health: () => apiFetch<{ status: string }>("/"),

  listAds: (query: { brand?: string; category?: string; status?: string; q?: string; limit?: number; offset?: number }) =>
    apiFetch<{ items: AdRecord[]; limit: number; offset: number }>(`/api/ads${params(query)}`),

  getAd: (adId: string) => apiFetch<AdDetail>(`/api/ads/${adId}`),

  getFrames: (adId: string) =>
    apiFetch<{ items: FrameRecord[] }>(`/api/ads/${adId}/frames`),

  getEvidence: (adId: string) =>
    apiFetch<{ classification_evidence: unknown[]; rule_triggers: unknown[] }>(
      `/api/ads/${adId}/evidence`
    ),

  getSimilar: (adId: string, k = 10) =>
    apiFetch<RelatedAds>(`/api/ads/${adId}/similar${params({ k })}`),

  patchAd: (
    adId: string,
    patch: {
      brand_name?: string | null;
      brand_confidence?: number | null;
      products_text?: string | null;
      primary_category?: string | null;
      subcategory?: string | null;
      decision?: string | null;
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

  uploadAd: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiFetch<{ ad_id: string; job_id: string | null; state: string; duplicate_of?: string }>(
      "/api/ads/upload",
      { method: "POST", body: form }
    );
  },

  getJob: (jobId: string) => apiFetch<JobRecord>(`/api/jobs/${jobId}`),

  cancelJob: (jobId: string) =>
    apiFetch<{ cancelled: boolean; job: JobRecord }>(`/api/jobs/${jobId}/cancel`, {
      method: "POST"
    }),

  search: (query: {
    q?: string;
    mode?: string;
    ad_id?: string;
    brand?: string;
    category?: string;
    status?: string;
    rerank?: boolean;
    k?: number;
  }) =>
    apiFetch<{ mode: string; strategy?: string; filtered_count?: number; items: SearchHit[] }>(
      `/api/search${params(query)}`
    ),

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
    )
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
