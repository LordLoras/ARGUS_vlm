import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { api } from "../lib/api-client";
import { compactEvidenceText, shortSourceId } from "../lib/entity-display";
import { LayersIcon } from "../lib/icons";
import type { EntityTaxonomyMappingSummary } from "../lib/types";
import { StatusPill } from "./ProductEntities";

export function TaxonomyMapping() {
  const mappingsQuery = useQuery({
    queryKey: ["entity-taxonomy-mappings"],
    queryFn: () => api.getEntityTaxonomyMappings(1000),
  });
  const mappings = mappingsQuery.data?.items ?? [];
  const stats = useMemo(() => summarizeMappings(mappings), [mappings]);

  return (
    <>
      <Topbar crumbs={["Experimental", "Taxonomy Mapping"]} />
      <div className="page entity-page">
        <section className="entity-hero">
          <div>
            <span className="entity-kicker">Many-to-many mappings</span>
            <h1 className="page-title">Taxonomy Mapping</h1>
            <p className="page-sub">
              Confidence-aware links from product and category entities into taxonomy rows. One entity can appear
              more than once when it maps to several taxonomy targets or when separate sources support the mapping.
            </p>
          </div>
          <div className="entity-stat-strip">
            <div className="entity-metric">
              <strong>{mappings.length}</strong>
              <span>Mappings</span>
            </div>
            <div className="entity-metric">
              <strong>{stats.entities}</strong>
              <span>Entities</span>
            </div>
            <div className="entity-metric">
              <strong>{stats.sources}</strong>
              <span>Sources</span>
            </div>
          </div>
        </section>

        {mappingsQuery.isLoading ? (
          <div className="entity-empty-line">Loading taxonomy mappings...</div>
        ) : mappings.length === 0 ? (
          <EmptyState icon={<LayersIcon size={18} />} title="No mappings yet" hint="Run the entity resolver first." />
        ) : (
          <div className="entity-table-wrap">
            <table className="entity-table entity-table-fixed entity-taxonomy-table">
              <thead>
                <tr>
                  <th>Entity</th>
                  <th>Taxonomy</th>
                  <th>Name</th>
                  <th>Confidence</th>
                  <th>Status</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {mappings.map(({ entity, mapping }) => (
                  <tr key={mapping.id}>
                    <td>
                      <span className="entity-cell-title">{entity.canonical_name}</span>
                      <span className="entity-row-sub">{entity.type}</span>
                    </td>
                    <td>
                      <span className="entity-cell-title">{mapping.taxonomy_type}</span>
                      <span className="entity-row-sub">{mapping.taxonomy_id}</span>
                    </td>
                    <td>{mapping.taxonomy_name || "Unnamed mapping"}</td>
                    <td className="entity-number-cell">{Math.round(mapping.confidence * 100)}%</td>
                    <td><StatusPill status={mapping.status} /></td>
                    <td>
                      <div className="entity-evidence-preview">
                        {compactEvidenceText(mapping.evidence_text) || "Source metadata only"}
                      </div>
                      <span className="entity-row-sub">{shortSourceId(mapping.source_id)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function summarizeMappings(items: EntityTaxonomyMappingSummary[]) {
  const entities = new Set<string>();
  const sources = new Set<string>();
  for (const item of items) {
    entities.add(item.entity.id);
    if (item.mapping.source_id) sources.add(item.mapping.source_id);
  }
  return { entities: entities.size, sources: sources.size };
}
