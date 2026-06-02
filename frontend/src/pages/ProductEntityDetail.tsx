import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { api } from "../lib/api-client";
import { CheckIcon, GraphIcon, XIcon } from "../lib/icons";
import type { EntityTaxonomyMapping, ProductPage } from "../lib/types";
import { StatusPill } from "./ProductEntities";

export function ProductEntityDetail() {
  const { productId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const productQuery = useQuery({
    queryKey: ["entity-product", productId],
    queryFn: () => api.getEntityProduct(productId ?? ""),
    enabled: Boolean(productId),
  });

  const reviewMutation = useMutation({
    mutationFn: (status: "confirmed_reviewed" | "rejected") =>
      status === "rejected"
        ? api.rejectEntity(productId ?? "")
        : api.reviewEntity(productId ?? "", status),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["entity-product", productId] });
      await queryClient.invalidateQueries({ queryKey: ["entity-products"] });
    },
  });

  const product = productQuery.data;

  return (
    <>
      <Topbar
        crumbs={["Experimental", "Product Entities", product?.node.canonical_name ?? "Detail"]}
        actions={
          <>
            <button className="btn" onClick={() => navigate("/experimental/products")}>Back</button>
            <button
              className="btn"
              disabled={!productId || reviewMutation.isPending}
              onClick={() => reviewMutation.mutate("rejected")}
            >
              <XIcon size={11} />
              <span>Reject</span>
            </button>
            <button
              className="btn btn-primary"
              disabled={!productId || reviewMutation.isPending}
              onClick={() => reviewMutation.mutate("confirmed_reviewed")}
            >
              <CheckIcon size={11} />
              <span>Mark reviewed</span>
            </button>
          </>
        }
      />
      <div className="page entity-page">
        {productQuery.isLoading ? (
          <div className="entity-empty-line">Loading product entity...</div>
        ) : !product ? (
          <EmptyState icon={<GraphIcon size={18} />} title="Product entity not found" />
        ) : (
          <ProductDetailBody product={product} />
        )}
      </div>
    </>
  );
}

function ProductDetailBody({ product }: { product: ProductPage }) {
  return (
    <>
      <section className="entity-detail-head">
        <div>
          <span className="entity-kicker">Canonical product</span>
          <h1 className="page-title">{product.node.canonical_name}</h1>
          <p className="page-sub">{product.node.description || "No generated description yet."}</p>
        </div>
        <StatusPill status={product.node.status} />
      </section>

      <section className="entity-detail-grid">
        <FactCard label="Brand" value={product.brand?.canonical_name} />
        <FactCard label="Owner" value={product.owner?.canonical_name} />
        <FactCard label="Category" value={product.category?.canonical_name} />
        <FactCard label="Confidence" value={`${Math.round(product.node.confidence * 100)}%`} />
      </section>

      <section className="entity-two-col">
        <Panel title="Taxonomy mappings">
          {product.taxonomy_mappings.length ? (
            <div className="entity-chip-list">
              {product.taxonomy_mappings.map((mapping) => <MappingChip key={mapping.id} mapping={mapping} />)}
            </div>
          ) : (
            <span className="entity-muted">No taxonomy mappings stored.</span>
          )}
        </Panel>
        <Panel title="Aliases">
          {product.aliases.length ? (
            <div className="entity-chip-list">
              {product.aliases.map((alias) => (
                <span key={alias.id} className="entity-chip">
                  {alias.alias}
                  <em>{Math.round(alias.confidence * 100)}%</em>
                </span>
              ))}
            </div>
          ) : (
            <span className="entity-muted">No aliases stored.</span>
          )}
        </Panel>
      </section>

      <section className="entity-two-col entity-two-col-wide">
        <Panel title="Evidence timeline">
          {product.observations.length ? (
            <div className="entity-evidence-list">
              {product.observations.map((obs) => (
                <div key={obs.id} className="entity-evidence-item">
                  <span>{obs.source}</span>
                  <strong>{obs.evidence_text}</strong>
                  <em>
                    {obs.ad_id}
                    {obs.time_ms != null ? ` at ${obs.time_ms}ms` : ""}
                  </em>
                </div>
              ))}
            </div>
          ) : (
            <span className="entity-muted">No ad-grounded observations stored.</span>
          )}
        </Panel>

        <Panel title="Related submitted ads">
          {product.related_ads.length ? (
            <div className="entity-ad-list">
              {product.related_ads.map((ad) => (
                <Link key={ad.ad_id} className="entity-ad-item" to={`/library?ad=${encodeURIComponent(ad.ad_id)}`}>
                  <strong>{ad.brand_name || ad.ad_id}</strong>
                  <span>{ad.products_text || "No product projection"}</span>
                  <em>{ad.first_evidence_text || `${ad.evidence_count} evidence items`}</em>
                </Link>
              ))}
            </div>
          ) : (
            <span className="entity-muted">No related submitted ads linked.</span>
          )}
        </Panel>
      </section>
    </>
  );
}

function MappingChip({ mapping }: { mapping: EntityTaxonomyMapping }) {
  return (
    <span className="entity-chip">
      {mapping.taxonomy_type}:{mapping.taxonomy_id}
      <em>{mapping.taxonomy_name || "unnamed"} - {Math.round(mapping.confidence * 100)}%</em>
    </span>
  );
}

function FactCard({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="entity-fact">
      <span>{label}</span>
      <strong>{value || "Unknown"}</strong>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="entity-panel">
      <div className="entity-panel-title">{title}</div>
      {children}
    </div>
  );
}
