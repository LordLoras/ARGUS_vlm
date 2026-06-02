import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { GraphIcon, SearchIcon, SparkleIcon } from "../lib/icons";
import type { ProductSummary } from "../lib/types";

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "candidate", label: "Candidates" },
  { value: "confirmed_unreviewed", label: "Confirmed, unreviewed" },
  { value: "confirmed_reviewed", label: "Reviewed" },
  { value: "rejected", label: "Rejected" },
];

export function ProductEntities() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const queryClient = useQueryClient();
  const health = useApiHealth();

  const productsQuery = useQuery({
    queryKey: ["entity-products", q, status],
    queryFn: () => api.listEntityProducts({ q: q || undefined, status: status || undefined, limit: 200 }),
  });

  const resolverMutation = useMutation({
    mutationFn: () => api.runEntityResolver({ fully_automatic: false, limit: 1000 }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["entity-products"] });
      await queryClient.invalidateQueries({ queryKey: ["entity-graph"] });
      await queryClient.invalidateQueries({ queryKey: ["entity-taxonomy-mappings"] });
    },
  });

  const products = productsQuery.data?.items ?? [];
  const stats = useMemo(() => summarize(products), [products]);

  return (
    <>
      <Topbar
        crumbs={["Experimental", "Product Entities"]}
        actions={
          <button
            className="btn btn-primary"
            disabled={resolverMutation.isPending}
            onClick={() => resolverMutation.mutate()}
          >
            <SparkleIcon size={11} />
            <span>{resolverMutation.isPending ? "Resolving" : "Run resolver"}</span>
          </button>
        }
      />
      <ApiOfflineBanner offline={health.isError} />

      <div className="page entity-page">
        <section className="entity-branch-banner">
          <div>
            <strong>Post-submission experimental feature in development</strong>
            <span>
              Running on this local FastAPI/Vite server while developed on the experimental Git branch.
              Writes stay in entity_graph.db; submitted ad records are read-only inputs.
            </span>
          </div>
          <Link to="/about#experimental-products">View home notice</Link>
        </section>

        <section className="entity-hero">
          <div>
            <span className="entity-kicker">Post-submission experimental graph DB</span>
            <h1 className="page-title">Product Entities</h1>
            <p className="page-sub">
              Canonical product nodes generated from submitted ad evidence and stored in the isolated entity graph.
              This page is active development work, separate from the submitted past submission demo routes.
            </p>
          </div>
          <div className="entity-stat-strip">
            <Metric label="Products" value={products.length} />
            <Metric label="Candidates" value={stats.candidates} />
            <Metric label="Mappings" value={stats.mappings} />
            <Metric label="Ad links" value={stats.relatedAds} />
          </div>
        </section>

        <section className="entity-toolbar">
          <label className="entity-search">
            <SearchIcon size={13} />
            <input
              value={q}
              onChange={(event) => setQ(event.target.value)}
              placeholder="Search product entities"
              aria-label="Search product entities"
            />
          </label>
          <select className="input entity-status-select" value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </section>

        {productsQuery.isLoading ? (
          <div className="entity-empty-line">Loading product graph...</div>
        ) : products.length === 0 ? (
          <EmptyState
            icon={<GraphIcon size={18} />}
            title="No product entities yet"
            hint="Run the resolver to build product nodes from the submitted ad database."
          />
        ) : (
          <div className="entity-table-wrap">
            <table className="entity-table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Brand</th>
                  <th>Owner</th>
                  <th>Category</th>
                  <th>Evidence</th>
                  <th>Mappings</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product) => (
                  <ProductRow key={product.node.id} product={product} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function ProductRow({ product }: { product: ProductSummary }) {
  return (
    <tr>
      <td>
        <Link className="entity-link-strong" to={`/experimental/products/${product.node.id}`}>
          {product.node.canonical_name}
        </Link>
        <div className="entity-row-sub">{product.node.description || "Generated description pending"}</div>
      </td>
      <td>{product.brand?.canonical_name ?? "Unassigned"}</td>
      <td>{product.owner?.canonical_name ?? "Unknown"}</td>
      <td>{product.category?.canonical_name ?? "Unmapped"}</td>
      <td>
        <span className="entity-count">{product.evidence_count}</span>
        <span className="entity-row-sub">{product.related_ads_count} ads</span>
      </td>
      <td>{product.taxonomy_mappings_count}</td>
      <td><StatusPill status={product.node.status} /></td>
    </tr>
  );
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`entity-status entity-status-${status}`}>{status.replace(/_/g, " ")}</span>;
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="entity-metric">
      <strong>{value.toLocaleString()}</strong>
      <span>{label}</span>
    </div>
  );
}

function summarize(products: ProductSummary[]) {
  return products.reduce(
    (acc, product) => {
      if (product.node.status === "candidate") acc.candidates += 1;
      acc.mappings += product.taxonomy_mappings_count;
      acc.relatedAds += product.related_ads_count;
      return acc;
    },
    { candidates: 0, mappings: 0, relatedAds: 0 }
  );
}
