import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { CategoryBadge } from "../components/shared/CategoryBadge";
import { EmptyState } from "../components/shared/EmptyState";
import { FrameThumbnail } from "../components/shared/FrameThumbnail";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { formatDuration } from "../lib/format";
import { EditIcon, LibraryIcon, SearchIcon } from "../lib/icons";
import type { SearchHit } from "../lib/types";

const MODES = [
  { key: "hybrid", label: "Hybrid" },
  { key: "visual_hybrid", label: "Visual + OCR" },
  { key: "keyword", label: "Keyword" },
  { key: "text", label: "Text vector" },
  { key: "visual", label: "Visual" }
] as const;

const STATUS_OPTIONS = [
  { value: "", label: "Any status" },
  { value: "completed", label: "Completed" },
  { value: "processing", label: "Processing" },
  { value: "failed", label: "Failed" },
  { value: "duplicate", label: "Duplicate" },
  { value: "new", label: "New" }
] as const;

export function SearchPage() {
  const [q, setQ] = useState("");
  const [adId, setAdId] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [mode, setMode] = useState<(typeof MODES)[number]["key"]>("hybrid");
  const [submitted, setSubmitted] = useState<{
    q: string;
    ad_id: string;
    brand: string;
    category: string;
    status: string;
    mode: string;
    rerank: boolean;
  } | null>(null);
  const navigate = useNavigate();
  const health = useApiHealth();

  const query = useQuery({
    queryKey: ["search", submitted],
    queryFn: () => api.search({ ...submitted!, k: 20 }),
    enabled: Boolean(submitted)
  });

  const canSubmit = Boolean(q || adId);
  const items = query.data?.items ?? [];
  const filteredCount = query.data?.filtered_count ?? 0;

  const openAd = (id: string, edit = false) => {
    navigate(`/library?ad=${encodeURIComponent(id)}${edit ? "&tab=edit" : ""}`);
  };

  return (
    <>
      <Topbar crumbs={["Workspace", "Search"]} />
      <ApiOfflineBanner offline={health.isError} />

      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Search</h1>
            <p className="page-sub">Keyword, vector text, hybrid, or visual retrieval over persisted ads.</p>
          </div>
        </div>

        <div className="search-panel">
          <div className="search-primary-row">
            <label className="search-field search-field-query">
              <span className="search-label">Query</span>
              <input
                className="input search-query"
                placeholder={
                  mode === "visual" || mode === "visual_hybrid"
                    ? "red car, product shot, outdoor scene..."
                    : "financing, health claim, brand..."
                }
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </label>
            <label className="search-field search-field-seed">
              <span className="search-label">Seed ad</span>
              <input
                className="input search-seed"
                placeholder="ad_..."
                value={adId}
                onChange={(e) => setAdId(e.target.value)}
              />
            </label>
            <button
              className="btn btn-primary search-submit"
              disabled={!canSubmit}
              onClick={() =>
                setSubmitted({
                  q,
                  ad_id: adId,
                  brand,
                  category,
                  status,
                  mode,
                  rerank: true
                })
              }
            >
              <SearchIcon size={13} />
              <span>Search</span>
            </button>
          </div>

          <div className="search-secondary-row">
            <div className="search-mode-group" aria-label="Search mode">
              {MODES.map((m) => (
                <button
                  key={m.key}
                  className={`search-mode ${mode === m.key ? "is-active" : ""}`}
                  onClick={() => setMode(m.key)}
                  type="button"
                >
                  {m.label}
                </button>
              ))}
            </div>

            <div className="search-filter-grid">
              <label className="search-field">
                <span className="search-label">Brand</span>
                <input
                  className="input search-filter"
                  placeholder="Any brand"
                  value={brand}
                  onChange={(e) => setBrand(e.target.value)}
                />
              </label>
              <label className="search-field">
                <span className="search-label">Category</span>
                <input
                  className="input search-filter"
                  placeholder="Any category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                />
              </label>
              <label className="search-field">
                <span className="search-label">Status</span>
                <select
                  className="input search-filter"
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  title="Pipeline state: completed, processing, failed, duplicate, or new."
                >
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option.value || "any"} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="search-status-note">
                Status is the pipeline state. Use Completed for finished ads.
              </div>
            </div>
          </div>
        </div>

        <div style={{ padding: 24, flex: 1, overflow: "auto" }}>
          {!submitted ? (
            <EmptyState
              icon={<SearchIcon size={18} />}
              title="Run a query"
              hint="Hybrid uses keyword-first matching for speed, with vector fallback when keywords do not hit."
            />
          ) : query.isLoading ? (
            <div className="obs-empty">Searching…</div>
          ) : items.length === 0 ? (
            <div className="obs-empty">No results for this query.</div>
          ) : (
            <div className="dcard">
              <div className="dcard-head">
                <span>{query.data?.mode ?? mode} results</span>
                {query.data?.strategy ? (
                  <span className="badge badge-mono">{query.data.strategy}</span>
                ) : null}
                <span className="count-pill">{items.length}</span>
                {filteredCount > 0 ? (
                  <span className="badge badge-mono" style={{ marginLeft: 4 }}>
                    {filteredCount} below relevance threshold
                  </span>
                ) : null}
              </div>
              <div className="search-results">
                {items.map((hit, idx) => (
                  <SearchResultRow
                    key={`${hit.ad_id}-${idx}`}
                    hit={hit}
                    index={idx}
                    onOpen={() => openAd(hit.ad_id)}
                    onEdit={() => openAd(hit.ad_id, true)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function SearchResultRow({
  hit,
  index,
  onOpen,
  onEdit
}: {
  hit: SearchHit;
  index: number;
  onOpen: () => void;
  onEdit: () => void;
}) {
  const ad = hit.ad;
  const title = ad?.brand_name || ad?.advertiser_name || hit.ad_id;
  const products = ad?.products_text || "No products extracted";
  const category = ad?.primary_category ?? "uncategorized";
  const metric = formatMetric(hit);

  return (
    <div
      className="search-result"
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
    >
      <span className="badge badge-mono search-rank">#{index + 1}</span>
      <FrameThumbnail
        path={hit.thumbnail_path}
        ar={ad?.width && ad.height ? `${ad.width}:${ad.height}` : undefined}
        seedA="#312e81"
        seedB="#155e75"
        className="search-thumb"
      />
      <div className="search-result-main">
        <div className="search-result-title">
          <span>{title}</span>
          <CategoryBadge category={category} />
          {hit.source ? <span className="badge">{hit.source}</span> : null}
        </div>
        <div className="search-result-products">{products}</div>
        <div className="search-result-meta">
          <span>{hit.ad_id}</span>
          <span>{formatDuration(ad?.duration_ms)}</span>
          {metric ? <span>{metric}</span> : null}
          {hit.matched_frames?.length ? (
            <span>
              frame {hit.matched_frames[0]?.frame_index} @ {formatDuration(hit.matched_frames[0]?.time_ms)}
            </span>
          ) : null}
          {hit.rerank_reason ? <span>{hit.rerank_reason}</span> : null}
        </div>
      </div>
      <div
        className="search-result-actions"
        onClick={(event) => event.stopPropagation()}
      >
        <button className="btn btn-sm" onClick={onOpen}>
          <LibraryIcon size={11} />
          <span>Open</span>
        </button>
        <button className="btn btn-sm btn-primary" onClick={onEdit}>
          <EditIcon size={11} />
          <span>Edit</span>
        </button>
      </div>
    </div>
  );
}

function formatMetric(hit: SearchHit) {
  if (hit.rerank_score != null) return `rerank ${hit.rerank_score.toFixed(3)}`;
  if (hit.score != null) return `score ${hit.score.toFixed(3)}`;
  if (hit.rrf_score != null) return `rrf ${hit.rrf_score.toFixed(3)}`;
  if (hit.distance != null) return `d ${hit.distance.toFixed(3)}`;
  if (hit.vec_distance != null) return `d ${hit.vec_distance.toFixed(3)}`;
  return "";
}
