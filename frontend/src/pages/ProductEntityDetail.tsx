import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { api } from "../lib/api-client";
import { compactEvidenceText } from "../lib/entity-display";
import { CheckIcon, EditIcon, GraphIcon, XIcon } from "../lib/icons";
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
          <p className="entity-context-note">
            Product entity page for canonical facts, aliases, taxonomy links, provenance, review status, and related
            submitted ads.
          </p>
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

      <ProductEditPanel product={product} />

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
                  <strong>{compactEvidenceText(obs.evidence_text)}</strong>
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
                  <em>{compactEvidenceText(ad.first_evidence_text) || `${ad.evidence_count} evidence items`}</em>
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

function ProductEditPanel({ product }: { product: ProductPage }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(() => draftFromProduct(product));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(draftFromProduct(product));
  }, [product.node.id, product.node.updated_at]);

  const brandSuggestions = useQuery({
    queryKey: ["entity-node-lookup", "brand"],
    queryFn: () => api.lookupEntityNodes({ entity_type: "brand", limit: 75 })
  });
  const ownerSuggestions = useQuery({
    queryKey: ["entity-node-lookup", "company"],
    queryFn: () => api.lookupEntityNodes({ entity_type: "company", limit: 75 })
  });
  const categorySuggestions = useQuery({
    queryKey: ["entity-node-lookup", "category"],
    queryFn: () => api.lookupEntityNodes({ entity_type: "category", limit: 75 })
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateEntityProduct(product.node.id, {
        canonical_name: draft.canonical_name,
        description: draft.description,
        status: draft.status,
        confidence: draft.confidence,
        brand_name: nullableText(draft.brand_name),
        owner_name: nullableText(draft.owner_name),
        category_name: nullableText(draft.category_name)
      }),
    onSuccess: async () => {
      setError(null);
      await queryClient.invalidateQueries({ queryKey: ["entity-product", product.node.id] });
      await queryClient.invalidateQueries({ queryKey: ["entity-products"] });
      await queryClient.invalidateQueries({ queryKey: ["entity-graph"] });
      await queryClient.invalidateQueries({ queryKey: ["entity-node-lookup"] });
    },
    onError: (nextError) =>
      setError(nextError instanceof Error ? nextError.message : "Product update failed")
  });

  return (
    <section className="entity-panel entity-edit-panel">
      <div className="entity-panel-title">Graph editor</div>
      <p className="entity-section-note">
        Edits here update the experimental product graph only. Use the crawler review page for
        approved submitted-record repairs.
      </p>
      <div className="entity-edit-grid">
        <label className="entity-field">
          <span>Canonical name</span>
          <input
            className="input"
            value={draft.canonical_name}
            onChange={(event) => setDraft({ ...draft, canonical_name: event.target.value })}
          />
        </label>
        <label className="entity-field">
          <span>Status</span>
          <select
            className="input"
            value={draft.status}
            onChange={(event) => setDraft({ ...draft, status: event.target.value as ProductPage["node"]["status"] })}
          >
            <option value="candidate">candidate</option>
            <option value="confirmed_unreviewed">confirmed_unreviewed</option>
            <option value="confirmed_reviewed">confirmed_reviewed</option>
            <option value="rejected">rejected</option>
          </select>
        </label>
        <label className="entity-field">
          <span>Confidence</span>
          <input
            className="input"
            type="number"
            min={0}
            max={1}
            step={0.01}
            value={draft.confidence}
            onChange={(event) =>
              setDraft({ ...draft, confidence: clampConfidence(Number(event.target.value)) })
            }
          />
        </label>
        <label className="entity-field">
          <span>Brand</span>
          <input
            className="input"
            list="entity-brand-suggestions"
            value={draft.brand_name}
            onChange={(event) => setDraft({ ...draft, brand_name: event.target.value })}
          />
        </label>
        <label className="entity-field">
          <span>Owner</span>
          <input
            className="input"
            list="entity-owner-suggestions"
            value={draft.owner_name}
            onChange={(event) => setDraft({ ...draft, owner_name: event.target.value })}
          />
        </label>
        <label className="entity-field">
          <span>Category</span>
          <input
            className="input"
            list="entity-category-suggestions"
            value={draft.category_name}
            onChange={(event) => setDraft({ ...draft, category_name: event.target.value })}
          />
        </label>
      </div>
      <label className="entity-field entity-edit-description">
        <span>Description</span>
        <textarea
          className="input entity-textarea"
          value={draft.description}
          onChange={(event) => setDraft({ ...draft, description: event.target.value })}
        />
      </label>
      <datalist id="entity-brand-suggestions">
        {(brandSuggestions.data?.items ?? []).map((node) => (
          <option key={node.id} value={node.canonical_name} />
        ))}
      </datalist>
      <datalist id="entity-owner-suggestions">
        {(ownerSuggestions.data?.items ?? []).map((node) => (
          <option key={node.id} value={node.canonical_name} />
        ))}
      </datalist>
      <datalist id="entity-category-suggestions">
        {(categorySuggestions.data?.items ?? []).map((node) => (
          <option key={node.id} value={node.canonical_name} />
        ))}
      </datalist>
      {error ? <div className="entity-error-line">{error}</div> : null}
      <div className="entity-action-row">
        <button
          className="btn btn-primary"
          disabled={saveMutation.isPending || !draft.canonical_name.trim()}
          onClick={() => saveMutation.mutate()}
        >
          <EditIcon size={11} />
          <span>{saveMutation.isPending ? "Saving" : "Save graph fields"}</span>
        </button>
        <button className="btn" disabled={saveMutation.isPending} onClick={() => setDraft(draftFromProduct(product))}>
          Reset form
        </button>
      </div>
    </section>
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

function draftFromProduct(product: ProductPage) {
  return {
    canonical_name: product.node.canonical_name,
    description: product.node.description || "",
    status: product.node.status,
    confidence: Number(product.node.confidence.toFixed(2)),
    brand_name: product.brand?.canonical_name || "",
    owner_name: product.owner?.canonical_name || "",
    category_name: product.category?.canonical_name || ""
  };
}

function nullableText(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function clampConfidence(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.min(Math.max(value, 0), 1);
}
