import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { SearchIcon } from "../lib/icons";

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
  const health = useApiHealth();

  const query = useQuery({
    queryKey: ["search", submitted],
    queryFn: () => api.search({ ...submitted!, k: 20 }),
    enabled: Boolean(submitted)
  });

  const canSubmit = mode === "visual" ? Boolean(adId) : Boolean(q || adId);

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
          <div className="row" style={{ gap: 8 }}>
            <input
              className="input"
              placeholder={mode === "visual" ? "(query ignored in visual mode)" : "financing, health claim, brand…"}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ flex: 1 }}
              disabled={mode === "visual"}
            />
            <input
              className="input"
              placeholder="seed ad id (optional)"
              value={adId}
              onChange={(e) => setAdId(e.target.value)}
              style={{ width: 220 }}
            />
            <div className="row" style={{ gap: 4 }}>
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
              hint="Hybrid combines BM25 + sqlite-vec via reciprocal rank fusion."
            />
          ) : query.isLoading ? (
            <div className="obs-empty">Searching…</div>
          ) : (query.data?.items ?? []).length === 0 ? (
            <div className="obs-empty">No results for this query.</div>
          ) : (
            <div className="dcard">
              <div className="dcard-head">
                <span>{query.data?.mode ?? mode} results</span>
                <span className="count-pill">{query.data?.items.length ?? 0}</span>
              </div>
              <div className="dcard-body">
                {(query.data?.items ?? []).map((hit, idx) => (
                  <div
                    key={`${hit.ad_id}-${idx}`}
                    className="row"
                    style={{
                      padding: "8px 0",
                      borderBottom: "1px solid var(--border)",
                      gap: 12
                    }}
                  >
                    <span className="badge badge-mono">#{idx + 1}</span>
                    <span className="mono" style={{ color: "var(--accent-2)", flex: 1 }}>
                      {hit.ad_id}
                    </span>
                    {hit.source ? <span className="badge">{hit.source}</span> : null}
                    {hit.score != null ? (
                      <span className="mono" style={{ color: "var(--fg-mute)" }}>
                        {hit.score.toFixed(3)}
                      </span>
                    ) : hit.distance != null ? (
                      <span className="mono" style={{ color: "var(--fg-mute)" }}>
                        d={hit.distance.toFixed(3)}
                      </span>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
