import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Topbar } from "../components/Topbar";
import { api } from "../lib/api-client";
import { CheckIcon, SparkleIcon } from "../lib/icons";
import type { ResolverResult } from "../lib/types";
import { StatusPill } from "./ProductEntities";

export function EntityResolver() {
  const [fullyAutomatic, setFullyAutomatic] = useState(false);
  const [candidateName, setCandidateName] = useState("");
  const [candidateUrl, setCandidateUrl] = useState("");
  const [result, setResult] = useState<ResolverResult | null>(null);
  const queryClient = useQueryClient();

  const readonlyQuery = useQuery({
    queryKey: ["entity-readonly-status"],
    queryFn: api.getEntityReadonlyStatus,
  });

  const previewMutation = useMutation({
    mutationFn: () => api.previewEntityResolver({ fully_automatic: fullyAutomatic, limit: 1000 }),
    onSuccess: setResult,
  });

  const runMutation = useMutation({
    mutationFn: () => api.runEntityResolver({ fully_automatic: fullyAutomatic, limit: 1000 }),
    onSuccess: async (next) => {
      setResult(next);
      await queryClient.invalidateQueries({ queryKey: ["entity-products"] });
      await queryClient.invalidateQueries({ queryKey: ["entity-graph"] });
      await queryClient.invalidateQueries({ queryKey: ["entity-taxonomy-mappings"] });
    },
  });

  const discoveryMutation = useMutation({
    mutationFn: () =>
      api.addDiscoveryCandidate({
        entity_type: "product",
        name: candidateName,
        source_url: candidateUrl || null,
        confidence: 0.35,
      }),
    onSuccess: async () => {
      setCandidateName("");
      setCandidateUrl("");
      await queryClient.invalidateQueries({ queryKey: ["entity-products"] });
    },
  });

  return (
    <>
      <Topbar crumbs={["Experimental", "Entity Resolver"]} />
      <div className="page entity-page">
        <section className="entity-hero">
          <div>
            <span className="entity-kicker">Automation with audit trail</span>
            <h1 className="page-title">Entity Resolver</h1>
            <p className="page-sub">
              Build product graph entries from submitted ad evidence. Search or web discoveries remain candidate-only.
            </p>
          </div>
          <div className="entity-readonly-badge">
            <CheckIcon size={12} />
            submitted DB query_only: {readonlyQuery.data?.submitted_db_query_only ? "on" : "checking"}
          </div>
        </section>

        <section className="entity-resolver-controls">
          <label className="entity-toggle">
            <input
              type="checkbox"
              checked={fullyAutomatic}
              onChange={(event) => setFullyAutomatic(event.target.checked)}
            />
            <span>Fully automatic mode marks grounded entries as unreviewed, not reviewed.</span>
          </label>
          <div className="entity-action-row">
            <button className="btn" disabled={previewMutation.isPending} onClick={() => previewMutation.mutate()}>
              Preview
            </button>
            <button className="btn btn-primary" disabled={runMutation.isPending} onClick={() => runMutation.mutate()}>
              <SparkleIcon size={11} />
              <span>{runMutation.isPending ? "Running" : "Run resolver"}</span>
            </button>
          </div>
        </section>

        <section className="entity-two-col">
          <div className="entity-panel">
            <div className="entity-panel-title">Discovery-only candidate</div>
            <div className="entity-form-grid">
              <input
                className="input"
                value={candidateName}
                onChange={(e) => setCandidateName(e.target.value)}
                placeholder="Candidate product name"
              />
              <input
                className="input"
                value={candidateUrl}
                onChange={(e) => setCandidateUrl(e.target.value)}
                placeholder="Optional source URL"
              />
              <button
                className="btn"
                disabled={!candidateName.trim() || discoveryMutation.isPending}
                onClick={() => discoveryMutation.mutate()}
              >
                Add candidate
              </button>
            </div>
          </div>

          <div className="entity-panel">
            <div className="entity-panel-title">Last resolver result</div>
            {result ? (
              <div className="entity-stat-strip entity-stat-strip-tight">
                <Metric label="Ads" value={result.source_ad_count} />
                <Metric label="Created" value={result.created_count} />
                <Metric label="Candidates" value={result.candidate_count} />
                <Metric label="Unreviewed" value={result.confirmed_unreviewed_count} />
              </div>
            ) : (
              <span className="entity-muted">Preview or run the resolver to see proposed entries.</span>
            )}
          </div>
        </section>

        {result?.items.length ? (
          <div className="entity-table-wrap">
            <table className="entity-table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Ad</th>
                  <th>Brand</th>
                  <th>Category</th>
                  <th>Status</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {result.items.slice(0, 200).map((item, index) => (
                  <tr key={`${item.ad_id}-${item.product_name}-${index}`}>
                    <td>{item.product_name}</td>
                    <td>{item.ad_id}</td>
                    <td>{item.brand_name || "Unknown"}</td>
                    <td>{item.category_name || "Unmapped"}</td>
                    <td><StatusPill status={item.status} /></td>
                    <td>{item.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </>
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
