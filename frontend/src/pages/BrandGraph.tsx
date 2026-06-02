import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { api } from "../lib/api-client";
import { GraphIcon } from "../lib/icons";
import type { EntityGraphPayload, EntityNode } from "../lib/types";

export function BrandGraph() {
  const graphQuery = useQuery({
    queryKey: ["entity-graph"],
    queryFn: () => api.getEntityGraph(800),
  });
  const graph = graphQuery.data;
  const stats = useMemo(() => summarizeGraph(graph), [graph]);
  const nodeMap = useMemo(
    () => new Map((graph?.nodes ?? []).map((node) => [node.id, node] as const)),
    [graph]
  );

  return (
    <>
      <Topbar crumbs={["Experimental", "Brand Graph"]} />
      <div className="page entity-page">
        <section className="entity-hero">
          <div>
            <span className="entity-kicker">Experimental relation graph</span>
            <h1 className="page-title">Brand Graph</h1>
            <p className="page-sub">
              Product, brand, company, category, taxonomy, and ad relations from the isolated graph store.
            </p>
          </div>
          <div className="entity-stat-strip">
            {Object.entries(stats.byType).map(([type, count]) => (
              <div key={type} className="entity-metric">
                <strong>{count}</strong>
                <span>{type}</span>
              </div>
            ))}
          </div>
        </section>

        {graphQuery.isLoading ? (
          <div className="entity-empty-line">Loading graph relations...</div>
        ) : !graph || graph.nodes.length === 0 ? (
          <EmptyState icon={<GraphIcon size={18} />} title="No graph nodes yet" hint="Run the entity resolver first." />
        ) : (
          <section className="entity-graph-board">
            <div className="entity-panel">
              <div className="entity-panel-title">Relationship ledger</div>
              <table className="entity-table">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Relation</th>
                    <th>Target</th>
                    <th>Confidence</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {graph.edges.map((edge) => {
                    const source = nodeMap.get(edge.source_node_id);
                    const target = nodeMap.get(edge.target_node_id);
                    return (
                      <tr key={edge.id}>
                        <td>{nodeLabel(source)}</td>
                        <td><span className="entity-relation">{edge.relation}</span></td>
                        <td>{nodeLabel(target)}</td>
                        <td>{Math.round(edge.confidence * 100)}%</td>
                        <td>{edge.status.replace(/_/g, " ")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </>
  );
}

function summarizeGraph(graph?: EntityGraphPayload) {
  const byType: Record<string, number> = {};
  for (const node of graph?.nodes ?? []) {
    byType[node.type] = (byType[node.type] ?? 0) + 1;
  }
  return { byType };
}

function nodeLabel(node?: EntityNode) {
  if (!node) return "Missing node";
  return `${node.canonical_name} (${node.type})`;
}
