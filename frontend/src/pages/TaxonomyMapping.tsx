import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { api } from "../lib/api-client";
import { LayersIcon } from "../lib/icons";
import { StatusPill } from "./ProductEntities";

export function TaxonomyMapping() {
  const mappingsQuery = useQuery({
    queryKey: ["entity-taxonomy-mappings"],
    queryFn: () => api.getEntityTaxonomyMappings(1000),
  });
  const mappings = mappingsQuery.data?.items ?? [];

  return (
    <>
      <Topbar crumbs={["Experimental", "Taxonomy Mapping"]} />
      <div className="page entity-page">
        <section className="entity-hero">
          <div>
            <span className="entity-kicker">Many-to-many mappings</span>
            <h1 className="page-title">Taxonomy Mapping</h1>
            <p className="page-sub">
              Confidence-aware product-to-taxonomy links with provenance stored in the experimental graph DB.
            </p>
          </div>
          <div className="entity-stat-strip">
            <div className="entity-metric">
              <strong>{mappings.length}</strong>
              <span>Mappings</span>
            </div>
          </div>
        </section>

        {mappingsQuery.isLoading ? (
          <div className="entity-empty-line">Loading taxonomy mappings...</div>
        ) : mappings.length === 0 ? (
          <EmptyState icon={<LayersIcon size={18} />} title="No mappings yet" hint="Run the entity resolver first." />
        ) : (
          <div className="entity-table-wrap">
            <table className="entity-table">
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
                    <td>{entity.canonical_name}</td>
                    <td>{mapping.taxonomy_type}:{mapping.taxonomy_id}</td>
                    <td>{mapping.taxonomy_name || "Unnamed mapping"}</td>
                    <td>{Math.round(mapping.confidence * 100)}%</td>
                    <td><StatusPill status={mapping.status} /></td>
                    <td>{mapping.evidence_text || "Source metadata only"}</td>
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
