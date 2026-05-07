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
  { key: "hybrid", label: "hybrid" },
  { key: "keyword", label: "keyword" },
  { key: "text", label: "text vector" },
  { key: "visual", label: "visual" }
] as const;

export function SearchPage() {
  const [q, setQ] = useState("");
  const [adId, setAdId] = useState("");
  const [mode, setMode] = useState<(typeof MODES)[number]["key"]>("hybrid");
  const [submitted, setSubmitted] = useState<{ q: string; ad_id: string; mode: string } | null>(null);
  const navigate = useNavigate();
  const health = useApiHealth();

  const query = useQuery({
    queryKey: ["search", submitted],
    queryFn: () => api.search({ ...submitted!, k: 20 }),
    enabled: Boolean(submitted)
  });

  const canSubmit = mode === "visual" ? Boolean(adId) : Boolean(q || adId);
  const items = query.data?.items ?? [];

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

        <div style={{ padding: "16px 24px", borderBottom: "1px solid var(--border)" }}>
          <div className="search-controls">
            <input
              className="input search-query"
              placeholder={mode === "visual" ? "(query ignored in visual mode)" : "financing, health claim, brand…"}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              disabled={mode === "visual"}
            />
            <input
              className="input search-seed"
              placeholder="seed ad id (optional)"
              value={adId}
              onChange={(e) => setAdId(e.target.value)}
            />
            <div className="search-modes">
              {MODES.map((m) => (
                <button
                  key={m.key}
                  className={`btn btn-sm ${mode === m.key ? "btn-primary" : ""}`}
                  onClick={() => setMode(m.key)}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <button
              className="btn btn-primary"
              disabled={!canSubmit}
              onClick={() => setSubmitted({ q, ad_id: adId, mode })}
            >
              <SearchIcon size={11} />
              <span>Search</span>
            </button>
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
  if (hit.score != null) return `score ${hit.score.toFixed(3)}`;
  if (hit.rrf_score != null) return `rrf ${hit.rrf_score.toFixed(3)}`;
  if (hit.distance != null) return `d ${hit.distance.toFixed(3)}`;
  if (hit.vec_distance != null) return `d ${hit.vec_distance.toFixed(3)}`;
  return "";
}
