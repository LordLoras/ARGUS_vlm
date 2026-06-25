import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { AlertIcon, CheckIcon, SearchIcon, XIcon } from "../lib/icons";
import type { IntelCrawlSummary, IntelSource, IntelTier } from "../lib/intel-types";

const TARGET_HINT: Record<string, string> = {
  youtube_channel: "Put the official channel id (UC…) in “Channel / platform id”.",
  rss: "Put the feed URL (newsroom/trade-press) in “URL”.",
  mock: "Offline test source (items come from config)."
};

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
        platform_id: platformId.trim() || null,
        enabled
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

  return (
    <>
      <Topbar crumbs={["Experimental", "Watcher"]} />
      <ApiOfflineBanner offline={health.isError} />

      <div className="page entity-page">
        <section className="entity-hero">
          <div>
            <span className="entity-kicker">Brand-anchored awareness crawler</span>
            <h1 className="page-title">Watcher</h1>
            <p className="page-sub">
              Curate the sources to watch per brand (YouTube channels, newsroom/trade-press feeds).
              First poll of a source is a baseline (records, no alerts); after that, genuinely new
              ad/campaign releases surface as signals.
            </p>
          </div>
          <div className="entity-stat-strip">
            <Metric label="Sources" value={sources.length} />
            <Metric label="Enabled" value={enabledCount} />
            <Metric label="Signals" value={signals.length} />
          </div>
        </section>

        <section className="entity-panel">
          <div className="entity-panel-title">Add a source</div>
          <div className="crawler-run-grid">
            <label className="entity-field">
              <span>Brand</span>
              <input
                className="input"
                value={brand}
                onChange={(event) => setBrand(event.target.value)}
                placeholder="Toyota"
              />
            </label>
            <label className="entity-field">
              <span>Type</span>
              <select
                className="input"
                value={sourceType}
                onChange={(event) => setSourceType(event.target.value)}
              >
                {sourceTypes.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
            <label className="entity-field">
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
            <label className="entity-field crawler-ad-field">
              <span>URL (feeds)</span>
              <input
                className="input"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://pressroom.toyota.com/product/feed/"
              />
            </label>
            <label className="entity-field crawler-ad-field">
              <span>Channel / platform id (YouTube)</span>
              <input
                className="input"
                value={platformId}
                onChange={(event) => setPlatformId(event.target.value)}
                placeholder="UC-official-channel-id"
              />
            </label>
            <label className="entity-field">
              <span>Enabled</span>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
                aria-label="Enabled"
              />
            </label>
            <div className="crawler-run-actions">
              <button
                className="btn btn-primary"
                disabled={!brand.trim() || createMutation.isPending}
                onClick={() => createMutation.mutate()}
              >
                <CheckIcon size={12} />
                <span>{createMutation.isPending ? "Adding" : "Add source"}</span>
              </button>
              <button
                className="btn"
                disabled={crawlBusy || enabledCount === 0}
                onClick={() => crawlAllMutation.mutate()}
              >
                <SearchIcon size={12} />
                <span>{crawlAllMutation.isPending ? "Crawling" : "Crawl all enabled"}</span>
              </button>
            </div>
          </div>
          <p className="entity-section-note">{TARGET_HINT[sourceType] ?? ""}</p>
          {error ? <div className="entity-error-line">{error}</div> : null}
          {lastRun ? (
            <div className="entity-stat-strip entity-stat-strip-tight crawler-run-result">
              <Metric label="Status" value={lastRun.status} />
              <Metric label="Sources" value={lastRun.source_count} />
              <Metric label="New resources" value={lastRun.resource_count} />
              <Metric label="New signals" value={lastRun.signal_count} />
            </div>
          ) : null}
        </section>

        <section className="entity-panel">
          <div className="entity-panel-title">Watched sources</div>
          {sourcesQuery.isLoading ? (
            <div className="entity-empty-line">Loading sources…</div>
          ) : sources.length === 0 ? (
            <EmptyState
              icon={<SearchIcon size={18} />}
              title="No sources yet"
              hint="Add a brand's official YouTube channel or newsroom feed above to start watching."
            />
          ) : (
            <div className="entity-table-wrap">
              <table className="entity-table">
                <thead>
                  <tr>
                    <th>Brand</th>
                    <th>Type</th>
                    <th>Target</th>
                    <th>Tier</th>
                    <th>State</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sources.map((source) => (
                    <tr key={source.id}>
                      <td>
                        <span className="entity-link-strong">{source.brand_name}</span>
                        <div className="entity-row-sub">{source.id}</div>
                      </td>
                      <td>
                        <span className="entity-chip">{source.source_type}</span>
                      </td>
                      <td>
                        <span className="entity-wrap-text">
                          {source.url || source.platform_id || "—"}
                        </span>
                      </td>
                      <td>{source.tier}</td>
                      <td>
                        <span
                          className={`entity-status entity-status-${
                            source.enabled ? "confirmed_unreviewed" : "candidate"
                          }`}
                        >
                          {source.enabled ? "enabled" : "disabled"}
                        </span>
                        <div className="entity-row-sub">
                          {source.source_activated_at ? "activated" : "baseline pending"}
                        </div>
                      </td>
                      <td>
                        <div className="entity-inline-actions">
                          <button
                            className="btn btn-compact"
                            disabled={crawlBusy}
                            onClick={() => crawlSourceMutation.mutate(source.id)}
                          >
                            <SearchIcon size={11} />
                            <span>Run</span>
                          </button>
                          <button
                            className="btn btn-compact"
                            disabled={toggleMutation.isPending}
                            onClick={() => toggleMutation.mutate(source)}
                          >
                            <span>{source.enabled ? "Disable" : "Enable"}</span>
                          </button>
                          <button
                            className="btn btn-compact"
                            disabled={deleteMutation.isPending}
                            onClick={() => deleteMutation.mutate(source.id)}
                          >
                            <XIcon size={11} />
                            <span>Delete</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="entity-panel">
          <div className="entity-panel-title">Signals</div>
          {signalsQuery.isLoading ? (
            <div className="entity-empty-line">Loading signals…</div>
          ) : signals.length === 0 ? (
            <EmptyState
              icon={<AlertIcon size={18} />}
              title="No signals yet"
              hint="Run a source twice: the first poll is baseline; new releases after that become signals."
            />
          ) : (
            <div className="entity-table-wrap">
              <table className="entity-table">
                <thead>
                  <tr>
                    <th>Brand</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Confidence</th>
                    <th>Title</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {signals.map((signal) => (
                    <tr key={signal.id}>
                      <td>
                        <span className="entity-link-strong">{signal.brand_name}</span>
                      </td>
                      <td>
                        <span className="entity-chip">{signal.signal_type}</span>
                      </td>
                      <td>
                        <span className={`entity-status entity-status-${signal.status}`}>
                          {signal.status}
                        </span>
                      </td>
                      <td>{Math.round(signal.confidence * 100)}%</td>
                      <td>
                        <span className="entity-wrap-text">
                          {signal.campaign_name || signal.title}
                        </span>
                        <div className="entity-row-sub">{formatDate(signal.source_published_at)}</div>
                      </td>
                      <td>
                        {signal.evidence[0]?.url ? (
                          <a
                            className="entity-link-strong"
                            href={signal.evidence[0].url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            open
                          </a>
                        ) : (
                          <span className="entity-muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="entity-metric">
      <strong>{typeof value === "number" ? value.toLocaleString() : value}</strong>
      <span>{label}</span>
    </div>
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
