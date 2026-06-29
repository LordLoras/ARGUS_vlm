import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CirclePlay,
  ExternalLink,
  Plus,
  Radio,
  Search,
  Trash2,
  ToggleLeft,
  ToggleRight
} from "lucide-react";
import { useState } from "react";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import type { IntelCrawlSummary, IntelSource, IntelTier } from "../lib/intel-types";
import "./Watcher.css";

const TARGET_HINT: Record<string, string> = {
  youtube_channel: "Put the official channel id (UC…) in “Channel / platform id”.",
  rss: "Put the feed URL (newsroom/trade-press) in “URL”.",
  meta_ad_library_ui:
    "Put the verified Meta page id in “Channel / page / platform id”. Defaults crawl active US ads; optional URL override can test a pasted Ad Library URL.",
  mock: "Offline test source (items come from config)."
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  meta_ad_library_ui: "Meta Ad Library",
  youtube_channel: "YouTube channel",
  rss: "RSS / newsroom feed",
  mock: "Mock source"
};

const META_DEFAULT_CONFIG = {
  active_status: "active",
  sort_mode: "relevancy_monthly_grouped",
  sort_direction: "desc",
  scrolls: 20,
  max_cards: 250,
  wait_ms: 1800,
  stop_after_no_new: 3
};

const META_SORT_LABELS: Record<string, string> = {
  relevancy_monthly_grouped: "Monthly relevancy",
  total_impressions: "Total impressions"
};

const SOURCE_PRESETS = [
  {
    label: "Toyota Meta",
    brand: "Toyota",
    sourceType: "meta_ad_library_ui",
    tier: "B" as IntelTier,
    platformId: "197052454200"
  },
  {
    label: "Jeep Meta",
    brand: "Jeep",
    sourceType: "meta_ad_library_ui",
    tier: "B" as IntelTier,
    platformId: "7037526514"
  }
];

function configForSourceType(sourceType: string): Record<string, unknown> {
  if (sourceType === "meta_ad_library_ui") {
    return { ...META_DEFAULT_CONFIG };
  }
  return {};
}

function platformForSourceType(sourceType: string): string | null {
  if (sourceType === "meta_ad_library_ui") return "meta";
  if (sourceType === "youtube_channel") return "youtube";
  return null;
}

function formatMetaSourceConfig(source: IntelSource) {
  const config = source.config ?? {};
  const status = String(config.active_status ?? META_DEFAULT_CONFIG.active_status);
  const sort = formatMetaSortMode(String(config.sort_mode ?? META_DEFAULT_CONFIG.sort_mode));
  const maxCards = String(config.max_cards ?? META_DEFAULT_CONFIG.max_cards);
  const scrolls = String(config.scrolls ?? META_DEFAULT_CONFIG.scrolls);
  return `${status} · ${sort} · ${scrolls} scrolls · ${maxCards} cards`;
}

function sourceTarget(source: IntelSource) {
  return source.url || source.platform_id || "No target configured";
}

function sourceStateLabel(source: IntelSource) {
  return source.source_activated_at ? "activated" : "baseline pending";
}

function sourceTypeLabel(sourceType: string) {
  return SOURCE_TYPE_LABELS[sourceType] ?? sourceType.replace(/_/g, " ");
}

function formatMetaSortMode(sortMode: string) {
  return META_SORT_LABELS[sortMode] ?? sortMode.replace(/_/g, " ");
}

function formatConfidence(value: number) {
  return `${Math.round(value * 100)}%`;
}

export function Watcher() {
  const health = useApiHealth();
  const queryClient = useQueryClient();

  const [brand, setBrand] = useState("");
  const [sourceType, setSourceType] = useState("youtube_channel");
  const [url, setUrl] = useState("");
  const [platformId, setPlatformId] = useState("");
  const [tier, setTier] = useState<IntelTier>("A");
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<IntelCrawlSummary | null>(null);

  const sourceTypesQuery = useQuery({
    queryKey: ["intel-source-types"],
    queryFn: () => api.listIntelSourceTypes()
  });
  const sourcesQuery = useQuery({
    queryKey: ["intel-sources"],
    queryFn: () => api.listIntelSources()
  });
  const signalsQuery = useQuery({
    queryKey: ["intel-signals"],
    queryFn: () => api.listIntelSignals({ limit: 100 })
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["intel-sources"] });
    void queryClient.invalidateQueries({ queryKey: ["intel-signals"] });
  };

  const createMutation = useMutation({
    mutationFn: () =>
      api.createIntelSource({
        brand: brand.trim(),
        source_type: sourceType,
        tier,
        url: url.trim() || null,
        platform: platformForSourceType(sourceType),
        platform_id: platformId.trim() || null,
        enabled,
        config: configForSourceType(sourceType)
      }),
    onSuccess: () => {
      setError(null);
      setBrand("");
      setUrl("");
      setPlatformId("");
      invalidate();
    },
    onError: (err) => setError(errorMessage(err))
  });

  const toggleMutation = useMutation({
    mutationFn: (source: IntelSource) => api.updateIntelSource(source.id, { enabled: !source.enabled }),
    onSuccess: invalidate,
    onError: (err) => setError(errorMessage(err))
  });
  const deleteMutation = useMutation({
    mutationFn: (sourceId: string) => api.deleteIntelSource(sourceId),
    onSuccess: invalidate,
    onError: (err) => setError(errorMessage(err))
  });
  const crawlSourceMutation = useMutation({
    mutationFn: (sourceId: string) => api.crawlIntelSource(sourceId),
    onSuccess: (summary) => {
      setError(null);
      setLastRun(summary);
      invalidate();
    },
    onError: (err) => setError(errorMessage(err))
  });
  const crawlAllMutation = useMutation({
    mutationFn: () => api.runIntelCrawl({ due: true }),
    onSuccess: (summary) => {
      setError(null);
      setLastRun(summary);
      invalidate();
    },
    onError: (err) => setError(errorMessage(err))
  });

  const sources = sourcesQuery.data?.items ?? [];
  const signals = signalsQuery.data?.items ?? [];
  const sourceTypes = sourceTypesQuery.data?.source_types ?? ["youtube_channel", "rss"];
  const enabledCount = sources.filter((source) => source.enabled).length;
  const crawlBusy = crawlAllMutation.isPending || crawlSourceMutation.isPending;
  const runningSourceId = crawlSourceMutation.isPending ? crawlSourceMutation.variables : null;
  const isMetaSource = sourceType === "meta_ad_library_ui";

  const applyPreset = (preset: (typeof SOURCE_PRESETS)[number]) => {
    setBrand(preset.brand);
    setSourceType(preset.sourceType);
    setTier(preset.tier);
    setPlatformId(preset.platformId);
    setUrl("");
    setEnabled(true);
  };

  return (
    <>
      <Topbar crumbs={["Experimental", "Watcher"]} />
      <ApiOfflineBanner offline={health.isError} />

      <div className="page watcher-page">
        <section className="watcher-hero">
          <div className="watcher-hero-copy">
            <span className="watcher-kicker">Brand intelligence</span>
            <h1 className="page-title">Watcher</h1>
            <p className="page-sub">
              Maintain brand source coverage, run active crawls, and review new campaign signals
              from one operational surface.
            </p>
          </div>
          <div className="watcher-metrics">
            <Metric label="Sources" value={sources.length} />
            <Metric label="Enabled" value={enabledCount} />
            <Metric label="Signals" value={signals.length} />
          </div>
        </section>

        <section className="watcher-panel watcher-add-panel">
          <div className="watcher-panel-header">
            <div>
              <span className="watcher-section-kicker">Source registry</span>
              <h2>Add a source</h2>
            </div>
            <div className="watcher-presets" aria-label="Source presets">
              {SOURCE_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  className="watcher-preset"
                  type="button"
                  onClick={() => applyPreset(preset)}
                >
                  <CheckCircle2 size={13} />
                  <span>{preset.label}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="watcher-form-grid">
            <label className="watcher-field">
              <span>Brand</span>
              <input
                className="input"
                value={brand}
                onChange={(event) => setBrand(event.target.value)}
                placeholder="Toyota"
              />
            </label>
            <label className="watcher-field">
              <span>Type</span>
              <select
                className="input"
                value={sourceType}
                onChange={(event) => setSourceType(event.target.value)}
              >
                {sourceTypes.map((type) => (
                  <option key={type} value={type}>
                    {sourceTypeLabel(type)}
                  </option>
                ))}
              </select>
            </label>
            <label className="watcher-field">
              <span>Tier</span>
              <select
                className="input"
                value={tier}
                onChange={(event) => setTier(event.target.value as IntelTier)}
              >
                <option value="A">A — strong</option>
                <option value="B">B — medium</option>
                <option value="C">C — corroboration</option>
              </select>
            </label>
            <label className="watcher-field watcher-wide-field">
              <span>{isMetaSource ? "URL override (optional)" : "URL (feeds)"}</span>
              <input
                className="input"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder={
                  isMetaSource
                    ? "Paste an Ad Library URL only when testing custom sort/filter params"
                    : "https://pressroom.toyota.com/product/feed/"
                }
              />
            </label>
            <label className="watcher-field watcher-wide-field">
              <span>Channel / page / platform id</span>
              <input
                className="input"
                value={platformId}
                onChange={(event) => setPlatformId(event.target.value)}
                placeholder="YouTube UC… or Meta page id"
              />
            </label>
            <label className="watcher-toggle">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
                aria-label="Enabled"
              />
              <span className="watcher-switch" aria-hidden="true" />
              <span>Enabled on create</span>
            </label>
            <div className="watcher-form-actions">
              <button
                className="watcher-primary-action"
                disabled={!brand.trim() || createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                <Plus size={14} />
                <span>{createMutation.isPending ? "Adding" : "Add source"}</span>
              </button>
              <button
                className="watcher-secondary-action"
                disabled={crawlBusy || enabledCount === 0}
                onClick={() => crawlAllMutation.mutate()}
              >
                <Search size={14} />
                <span>{crawlAllMutation.isPending ? "Crawling" : "Crawl all enabled"}</span>
              </button>
            </div>
          </div>
          <p className="watcher-help">{TARGET_HINT[sourceType] ?? ""}</p>
          {isMetaSource ? (
            <div className="watcher-config-strip">
              <ConfigPill label="Status" value={String(META_DEFAULT_CONFIG.active_status)} />
              <ConfigPill label="Sort" value={formatMetaSortMode(String(META_DEFAULT_CONFIG.sort_mode))} />
              <ConfigPill label="Max scrolls" value={String(META_DEFAULT_CONFIG.scrolls)} />
              <ConfigPill label="Card cap" value={String(META_DEFAULT_CONFIG.max_cards)} />
            </div>
          ) : null}
          {error ? <div className="watcher-error">{error}</div> : null}
          {lastRun ? (
            <div className="watcher-run-summary">
              <Metric label="Status" value={lastRun.status} />
              <Metric label="Sources" value={lastRun.source_count} />
              <Metric label="New resources" value={lastRun.resource_count} />
              <Metric label="New signals" value={lastRun.signal_count} />
            </div>
          ) : null}
        </section>

        <section className="watcher-panel">
          <div className="watcher-panel-header">
            <div>
              <span className="watcher-section-kicker">Registry</span>
              <h2>Watched sources</h2>
            </div>
          </div>
          {sourcesQuery.isLoading ? (
            <div className="watcher-muted-line">Loading sources…</div>
          ) : sources.length === 0 ? (
            <EmptyState
              icon={<Search size={18} />}
              title="No sources yet"
              hint="Add a Meta page id, official YouTube channel, or newsroom feed above to start watching."
            />
          ) : (
            <div className="watcher-source-grid">
              {sources.map((source) => (
                <article
                  className={`watcher-source-card ${source.enabled ? "is-enabled" : ""}`}
                  key={source.id}
                >
                  <div className="watcher-source-card-head">
                    <div>
                      <strong>{source.brand_name}</strong>
                      <span>{sourceTypeLabel(source.source_type)} source</span>
                    </div>
                    <span className={`watcher-state-pill ${source.enabled ? "enabled" : "disabled"}`}>
                      {source.enabled ? "enabled" : "disabled"}
                    </span>
                  </div>
                  <div className="watcher-source-tags">
                    <span>{sourceTypeLabel(source.source_type)}</span>
                    <span>Tier {source.tier}</span>
                    <span>{sourceStateLabel(source)}</span>
                  </div>
                  <div className="watcher-target-card">
                    <span>Target</span>
                    <strong>{sourceTarget(source)}</strong>
                    {source.source_type === "meta_ad_library_ui" ? (
                      <em>{formatMetaSourceConfig(source)}</em>
                    ) : null}
                  </div>
                  <div className="watcher-source-actions">
                    <button
                      className="watcher-card-action"
                      disabled={crawlBusy}
                      onClick={() => crawlSourceMutation.mutate(source.id)}
                    >
                      <CirclePlay size={14} />
                      <span>{runningSourceId === source.id ? "Running" : "Run"}</span>
                    </button>
                    <button
                      className="watcher-card-action"
                      disabled={toggleMutation.isPending}
                      onClick={() => toggleMutation.mutate(source)}
                    >
                      {source.enabled ? <ToggleLeft size={14} /> : <ToggleRight size={14} />}
                      <span>{source.enabled ? "Disable" : "Enable"}</span>
                    </button>
                    <button
                      className="watcher-card-action danger"
                      disabled={deleteMutation.isPending}
                      onClick={() => deleteMutation.mutate(source.id)}
                    >
                      <Trash2 size={14} />
                      <span>Delete</span>
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="watcher-panel">
          <div className="watcher-panel-header">
            <div>
              <span className="watcher-section-kicker">Activity</span>
              <h2>Signals</h2>
            </div>
          </div>
          {signalsQuery.isLoading ? (
            <div className="watcher-muted-line">Loading signals…</div>
          ) : signals.length === 0 ? (
            <EmptyState
              icon={<AlertTriangle size={18} />}
              title="No signals yet"
              hint="Run a source twice: the first poll is baseline; new releases after that become signals."
            />
          ) : (
            <div className="watcher-signal-list">
              {signals.map((signal) => (
                <article className="watcher-signal-card" key={signal.id}>
                  <div className="watcher-signal-icon">
                    <Radio size={16} />
                  </div>
                  <div className="watcher-signal-main">
                    <div className="watcher-signal-title">
                      <strong>{signal.campaign_name || signal.title}</strong>
                      <span>{signal.brand_name}</span>
                    </div>
                    <div className="watcher-source-tags">
                      <span>{signal.signal_type}</span>
                      <span>{signal.status}</span>
                      <span>{formatConfidence(signal.confidence)}</span>
                      {signal.source_published_at ? (
                        <span>{formatDate(signal.source_published_at)}</span>
                      ) : null}
                    </div>
                  </div>
                  {signal.evidence[0]?.url ? (
                    <a
                      className="watcher-card-action"
                      href={signal.evidence[0].url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <ExternalLink size={14} />
                      <span>Open</span>
                    </a>
                  ) : (
                    <span className="watcher-muted-line">No evidence URL</span>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="watcher-metric">
      <strong>{typeof value === "number" ? value.toLocaleString() : value}</strong>
      <span>{label}</span>
    </div>
  );
}

function ConfigPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="watcher-config-pill">
      <Activity size={12} />
      <span>{label}</span>
      <strong>{value}</strong>
    </span>
  );
}

function formatDate(value: string | null | undefined) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(0, 10);
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Request failed";
}
