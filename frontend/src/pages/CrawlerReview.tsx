import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { compactEvidenceText } from "../lib/entity-display";
import { AlertIcon, CheckIcon, EditIcon, FlowIcon, SearchIcon, XIcon } from "../lib/icons";
import type { AdChangeSuggestion, CrawlerResult, SubmittedAdCrawlQueueItem } from "../lib/types";

const STATUS_OPTIONS = [
  { value: "", label: "All suggestions" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "applied", label: "Applied" },
  { value: "rejected", label: "Rejected" }
];

const QUEUE_STATUS_OPTIONS = [
  { value: "ready", label: "Ready" },
  { value: "needs_review", label: "Needs review" },
  { value: "done", label: "Done" },
  { value: "no_targets", label: "No targets" },
  { value: "", label: "All" }
];

export function CrawlerReview() {
  const [limit, setLimit] = useState(1000);
  const [queueSearch, setQueueSearch] = useState("");
  const [queueStatus, setQueueStatus] = useState("ready");
  const [adIds, setAdIds] = useState("");
  const [referenceUrls, setReferenceUrls] = useState("");
  const [selectedAdIds, setSelectedAdIds] = useState<Set<string>>(new Set());
  const [status, setStatus] = useState("pending");
  const [filterAdId, setFilterAdId] = useState("");
  const [lastRun, setLastRun] = useState<CrawlerResult | null>(null);
  const [editedValues, setEditedValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const health = useApiHealth();

  const queueQuery = useQuery({
    queryKey: ["entity-crawler-queue", queueSearch, limit],
    queryFn: () => api.listEntityCrawlerQueue({ q: queueSearch || undefined, limit })
  });

  const suggestionsQuery = useQuery({
    queryKey: ["ad-change-suggestions", status, filterAdId],
    queryFn: () =>
      api.listAdChangeSuggestions({
        status: status || undefined,
        ad_id: filterAdId || undefined,
        limit: 500
      })
  });

  const allQueueItems = queueQuery.data?.items ?? [];
  const queueCounts = useMemo(() => summarizeQueue(allQueueItems), [allQueueItems]);
  const queueItems = useMemo(
    () =>
      queueStatus
        ? allQueueItems.filter((item) => item.crawl_status === queueStatus)
        : allQueueItems,
    [allQueueItems, queueStatus]
  );
  const visibleAdIds = queueItems.map((item) => item.ad_id);
  const explicitAdIds = parseAdIds(adIds);
  const selectedVisibleCount = visibleAdIds.filter((adId) => selectedAdIds.has(adId)).length;
  const selectedForRun = mergeAdIds([
    ...visibleAdIds.filter((adId) => selectedAdIds.has(adId)),
    ...explicitAdIds
  ]);

  const runMutation = useMutation({
    mutationFn: (mode: "visible" | "selected") => {
      const ids = mode === "visible" ? visibleAdIds : selectedForRun;
      return api.runEntityCrawler({
        limit,
        ad_ids: ids,
        targets: buildTargets(ids, referenceUrls)
      });
    },
    onSuccess: async (result) => {
      setError(null);
      setLastRun(result);
      await queryClient.invalidateQueries({ queryKey: ["ad-change-suggestions"] });
      await queryClient.invalidateQueries({ queryKey: ["entity-crawler-queue"] });
      await queryClient.invalidateQueries({ queryKey: ["entity-products"] });
      await queryClient.invalidateQueries({ queryKey: ["entity-graph"] });
    },
    onError: (nextError) => setError(errorMessage(nextError))
  });

  const suggestionSuccess = async () => {
    setError(null);
    await queryClient.invalidateQueries({ queryKey: ["ad-change-suggestions"] });
    await queryClient.invalidateQueries({ queryKey: ["entity-crawler-queue"] });
    await queryClient.invalidateQueries({ queryKey: ["entity-products"] });
  };

  const approveMutation = useMutation({
    mutationFn: (suggestion: AdChangeSuggestion) => api.approveAdChangeSuggestion(suggestion.id),
    onSuccess: suggestionSuccess,
    onError: (nextError) => setError(errorMessage(nextError))
  });

  const rejectMutation = useMutation({
    mutationFn: (suggestion: AdChangeSuggestion) => api.rejectAdChangeSuggestion(suggestion.id),
    onSuccess: suggestionSuccess,
    onError: (nextError) => setError(errorMessage(nextError))
  });

  const applyMutation = useMutation({
    mutationFn: (suggestion: AdChangeSuggestion) =>
      api.applyAdChangeSuggestion(
        suggestion.id,
        editedValues[suggestion.id] || suggestion.suggested_value
      ),
    onSuccess: suggestionSuccess,
    onError: (nextError) => setError(errorMessage(nextError))
  });

  const suggestions = suggestionsQuery.data?.items ?? [];
  const stats = useMemo(() => summarizeSuggestions(suggestions), [suggestions]);
  const allVisibleSelected =
    visibleAdIds.length > 0 && visibleAdIds.every((adId) => selectedAdIds.has(adId));

  return (
    <>
      <Topbar crumbs={["Experimental", "Crawler Review"]} />
      <ApiOfflineBanner offline={health.isError} />

      <div className="page entity-page">
        <section className="entity-hero">
          <div>
            <span className="entity-kicker">Experimental crawler and repair queue</span>
            <h1 className="page-title">Crawler Review</h1>
            <p className="page-sub">
              Queue submitted ads for discovery-only web/VLM enrichment. Crawler facts strengthen the
              product graph; submitted ad repairs are written only after a suggestion is approved and
              applied.
            </p>
          </div>
          <div className="entity-stat-strip">
            <Metric label="Pending" value={stats.pending} />
            <Metric label="Approved" value={stats.approved} />
            <Metric label="Applied" value={stats.applied} />
            <Metric label="Rejected" value={stats.rejected} />
          </div>
        </section>

        <section className="entity-panel crawler-run-panel">
          <div className="entity-panel-title">Submitted ad crawl queue</div>
          <div className="crawler-run-grid crawler-run-grid-queue">
            <label className="entity-field">
              <span>Limit</span>
              <input
                className="input"
                type="number"
                min={1}
                max={10000}
                value={limit}
                onChange={(event) => setLimit(Number(event.target.value) || 1)}
              />
            </label>
            <label className="entity-field crawler-ad-field">
              <span>Search queue</span>
              <input
                className="input"
                value={queueSearch}
                onChange={(event) => setQueueSearch(event.target.value)}
                placeholder="ad ID, brand, product, category"
              />
            </label>
            <label className="entity-field crawler-ad-field">
              <span>Extra ad IDs</span>
              <input
                className="input"
                value={adIds}
                onChange={(event) => setAdIds(event.target.value)}
                placeholder="ad_3271eca8, ad_203a2d73"
              />
            </label>
            <label className="entity-field crawler-url-field">
              <span>Ad-bound reference URLs</span>
              <textarea
                className="input entity-textarea"
                value={referenceUrls}
                onChange={(event) => setReferenceUrls(event.target.value)}
                placeholder="ad_3271eca8 https://www.apple.com/iphone-17-pro/"
              />
            </label>
            <div className="crawler-run-actions">
              <button
                className="btn"
                disabled={runMutation.isPending || visibleAdIds.length === 0}
                onClick={() => runMutation.mutate("visible")}
              >
                <FlowIcon size={12} />
                <span>{runMutation.isPending ? "Running" : "Run visible queue"}</span>
              </button>
              <button
                className="btn btn-primary"
                disabled={runMutation.isPending || selectedForRun.length === 0}
                onClick={() => runMutation.mutate("selected")}
              >
                <SearchIcon size={12} />
                <span>{runMutation.isPending ? "Running" : "Run selected"}</span>
              </button>
            </div>
          </div>
          {error ? <div className="entity-error-line">{error}</div> : null}
          <div className="entity-tab-strip entity-queue-tabs" aria-label="Crawler queue status">
            {QUEUE_STATUS_OPTIONS.map((option) => (
              <button
                key={option.value || "all"}
                className={`entity-tab ${queueStatus === option.value ? "active" : ""}`}
                onClick={() => setQueueStatus(option.value)}
                type="button"
              >
                <span>{option.label}</span>
                <strong>{queueCounts[option.value || "all"] ?? 0}</strong>
              </button>
            ))}
          </div>
          <div className="entity-action-row entity-queue-actions">
            <button
              className="btn btn-compact"
              disabled={visibleAdIds.length === 0}
              onClick={() => {
                setSelectedAdIds((current) => {
                  const next = new Set(current);
                  if (allVisibleSelected) {
                    visibleAdIds.forEach((adId) => next.delete(adId));
                  } else {
                    visibleAdIds.forEach((adId) => next.add(adId));
                  }
                  return next;
                });
              }}
            >
              {allVisibleSelected ? "Clear visible" : "Select visible"}
            </button>
            <span className="entity-muted">
              {selectedVisibleCount} selected from {visibleAdIds.length} loaded ads
            </span>
          </div>
          {lastRun ? (
            <div className="entity-stat-strip entity-stat-strip-tight crawler-run-result">
              <Metric label="Visited" value={lastRun.visited_count} />
              <Metric label="Skipped" value={lastRun.skipped_count} />
              <Metric label="Failed" value={lastRun.failed_count} />
              <Metric label="Observations" value={lastRun.observation_count} />
              <Metric label="Suggestions" value={lastRun.suggestion_count} />
            </div>
          ) : null}
          <CrawlerQueueTable
            items={queueItems}
            loading={queueQuery.isLoading}
            selectedAdIds={selectedAdIds}
            toggle={(adId) =>
              setSelectedAdIds((current) => {
                const next = new Set(current);
                if (next.has(adId)) next.delete(adId);
                else next.add(adId);
                return next;
              })
            }
          />
        </section>

        <section className="entity-panel">
          <div className="entity-panel-title">Submitted ad repair suggestions</div>
          <p className="entity-section-note">
            Crawler/VLM mismatches appear here for review. Existing submitted ad projections are
            changed only after a suggestion is approved and applied.
          </p>
          <div className="entity-repair-toolbar">
            <select
              className="input entity-status-select"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <label className="entity-search">
              <SearchIcon size={13} />
              <input
                value={filterAdId}
                onChange={(event) => setFilterAdId(event.target.value)}
                placeholder="Filter suggestions by ad ID"
                aria-label="Filter suggestions by ad ID"
              />
            </label>
          </div>
        </section>

        {suggestionsQuery.isLoading ? (
          <div className="entity-empty-line">Loading crawler suggestions...</div>
        ) : suggestions.length === 0 ? (
          <EmptyState
            icon={<AlertIcon size={18} />}
            title="No suggestions in this view"
            hint="Run the crawler with web/VLM verification to queue submitted-record corrections."
          />
        ) : (
          <div className="entity-table-wrap">
            <table className="entity-table entity-suggestion-table">
              <thead>
                <tr>
                  <th>Ad</th>
                  <th>Field</th>
                  <th>Current</th>
                  <th>Suggested / editable</th>
                  <th>Evidence</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {suggestions.map((suggestion) => (
                  <SuggestionRow
                    key={suggestion.id}
                    suggestion={suggestion}
                    editedValue={editedValues[suggestion.id] ?? suggestion.suggested_value}
                    setEditedValue={(value) =>
                      setEditedValues((current) => ({ ...current, [suggestion.id]: value }))
                    }
                    approve={() => approveMutation.mutate(suggestion)}
                    reject={() => rejectMutation.mutate(suggestion)}
                    apply={() => applyMutation.mutate(suggestion)}
                    busy={approveMutation.isPending || rejectMutation.isPending || applyMutation.isPending}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function CrawlerQueueTable({
  items,
  loading,
  selectedAdIds,
  toggle
}: {
  items: SubmittedAdCrawlQueueItem[];
  loading: boolean;
  selectedAdIds: Set<string>;
  toggle: (adId: string) => void;
}) {
  if (loading) {
    return <div className="entity-empty-line">Loading submitted ad queue...</div>;
  }
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<SearchIcon size={18} />}
        title="No submitted ads in queue"
        hint="Ads with submitted product metadata appear here after ingest or resolver rebuild."
      />
    );
  }
  return (
    <div className="entity-table-wrap">
      <table className="entity-table entity-crawler-queue-table">
        <thead>
          <tr>
            <th>Select</th>
            <th>Ad</th>
            <th>Products</th>
            <th>Category context</th>
            <th>Targets</th>
            <th>Graph work</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.ad_id}>
              <td>
                <input
                  type="checkbox"
                  checked={selectedAdIds.has(item.ad_id)}
                  onChange={() => toggle(item.ad_id)}
                  aria-label={`Select ${item.ad_id}`}
                />
              </td>
              <td>
                <span className="entity-link-strong">{item.ad_id}</span>
                <div className="entity-row-sub">{item.brand_name || "No submitted brand"}</div>
              </td>
              <td>
                <TextCell value={item.products_text || "No product projection"} />
                <div className="entity-row-sub">{item.product_count} extracted products</div>
              </td>
              <td>
                <span className="entity-chip entity-chip-inline">
                  {item.subcategory || item.primary_category || "None"}
                </span>
              </td>
              <td>
                <span className={item.has_web_targets ? "entity-status entity-status-confirmed_unreviewed" : "entity-status"}>
                  {item.has_web_targets ? "has targets" : "needs search"}
                </span>
                {item.web_targets[0] ? (
                  <div className="entity-row-sub">{compactEvidenceText(item.web_targets[0])}</div>
                ) : null}
              </td>
              <td>
                <span className={`entity-status entity-status-${item.crawl_status}`}>
                  {formatQueueStatus(item.crawl_status)}
                </span>
                <span className="entity-count">{item.pending_suggestion_count} pending repairs</span>
                <div className="entity-row-sub">
                  {item.last_crawled_at
                    ? `${item.crawled_source_count} sources, last crawled ${item.last_crawled_at}`
                    : "not crawled yet"}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SuggestionRow({
  suggestion,
  editedValue,
  setEditedValue,
  approve,
  reject,
  apply,
  busy
}: {
  suggestion: AdChangeSuggestion;
  editedValue: string;
  setEditedValue: (value: string) => void;
  approve: () => void;
  reject: () => void;
  apply: () => void;
  busy: boolean;
}) {
  return (
    <tr>
      <td>
        <span className="entity-link-strong">{suggestion.ad_id}</span>
        <div className="entity-row-sub">{Math.round(suggestion.confidence * 100)}% confidence</div>
      </td>
      <td>
        <span className="entity-chip">{suggestion.field_path}</span>
        <div className="entity-row-sub">{suggestion.apply_safety.replace(/_/g, " ")}</div>
      </td>
      <td><TextCell value={suggestion.current_value || "Empty"} /></td>
      <td>
        <textarea
          className="input entity-suggestion-value"
          value={editedValue}
          onChange={(event) => setEditedValue(event.target.value)}
          disabled={suggestion.status === "applied" || suggestion.status === "rejected"}
        />
      </td>
      <td>
        <TextCell value={suggestion.reason} />
        {suggestion.evidence_text ? <div className="entity-row-sub">{suggestion.evidence_text}</div> : null}
      </td>
      <td><span className={`entity-status entity-status-${suggestion.status}`}>{suggestion.status}</span></td>
      <td>
        <div className="entity-inline-actions">
          <button className="btn btn-compact" disabled={busy || suggestion.status !== "pending"} onClick={approve}>
            <CheckIcon size={11} />
            <span>Approve</span>
          </button>
          <button className="btn btn-compact" disabled={busy || suggestion.status !== "pending"} onClick={reject}>
            <XIcon size={11} />
            <span>Reject</span>
          </button>
          <button className="btn btn-compact btn-primary" disabled={busy || suggestion.status !== "approved"} onClick={apply}>
            <EditIcon size={11} />
            <span>Apply</span>
          </button>
        </div>
      </td>
    </tr>
  );
}

function TextCell({ value }: { value: string }) {
  return <span className="entity-wrap-text">{value}</span>;
}

function summarizeQueue(items: SubmittedAdCrawlQueueItem[]) {
  const counts: Record<string, number> = {
    all: items.length,
    ready: 0,
    needs_review: 0,
    done: 0,
    no_targets: 0
  };
  for (const item of items) {
    counts[item.crawl_status] = (counts[item.crawl_status] ?? 0) + 1;
  }
  return counts;
}

function formatQueueStatus(value: SubmittedAdCrawlQueueItem["crawl_status"]) {
  return value.replace(/_/g, " ");
}

function parseAdIds(value: string) {
  return value
    .split(/[,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function mergeAdIds(values: string[]) {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

function buildTargets(adIds: string[], value: string) {
  const lines = parseTargetLines(value);
  if (!lines.length) return [];
  const singleAdId = adIds.length === 1 ? adIds[0] : "";
  return lines.map((line) => {
    const matched = line.match(/^(ad_[A-Za-z0-9_-]+)[,\s]+(.+)$/);
    if (matched) {
      return { ad_id: matched[1], url: matched[2].trim() };
    }
    if (singleAdId) {
      return { ad_id: singleAdId, url: line };
    }
    throw new Error("Reference URL lines must start with an ad ID when multiple ads are selected.");
  });
}

function parseTargetLines(value: string) {
  return value
    .split(/\n+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function summarizeSuggestions(suggestions: AdChangeSuggestion[]) {
  return suggestions.reduce(
    (acc, suggestion) => {
      acc[suggestion.status] += 1;
      return acc;
    },
    { pending: 0, approved: 0, applied: 0, rejected: 0 }
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="entity-metric">
      <strong>{value.toLocaleString()}</strong>
      <span>{label}</span>
    </div>
  );
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Request failed";
}
