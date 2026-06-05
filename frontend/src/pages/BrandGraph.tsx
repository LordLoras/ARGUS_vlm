import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { api } from "../lib/api-client";
import { GraphIcon } from "../lib/icons";
import type { EntityEdge, EntityGraphPayload, EntityNode } from "../lib/types";
import { StatusPill } from "./ProductEntities";

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
  const relationRows = useMemo(() => groupRelations(graph?.edges ?? []), [graph]);

  return (
    <>
      <Topbar crumbs={["Experimental", "Brand Graph"]} />
      <div className="page entity-page">
        <section className="entity-hero">
          <div>
            <span className="entity-kicker">Experimental relation graph</span>
            <h1 className="page-title">Brand Graph</h1>
            <p className="page-sub">
              Typed edges between products, brands, owners, categories, taxonomy nodes, and submitted ads.
              Rows are grouped by logical relation; observation counts show how many source-specific edges support it.
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
              <div className="entity-section-note">
                Repeated-looking products usually mean different source ads, taxonomy targets, or relation types,
                not duplicate product nodes.
              </div>
              <table className="entity-table entity-table-fixed entity-graph-table">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Relation</th>
                    <th>Target</th>
                    <th>Observations</th>
                    <th>Confidence</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {relationRows.map((row) => {
                    const source = nodeMap.get(row.sourceNodeId);
                    const target = nodeMap.get(row.targetNodeId);
                    return (
                      <tr key={row.key}>
                        <td>{nodeLabel(source)}</td>
                        <td><span className="entity-relation">{row.relation}</span></td>
                        <td>{nodeLabel(target)}</td>
                        <td>
                          <span className="entity-count">{row.count}</span>
                          <span className="entity-row-sub">
                            {row.sources.size ? `${row.sources.size} sources` : "source metadata"}
                          </span>
                        </td>
                        <td className="entity-number-cell">{Math.round(row.confidence * 100)}%</td>
                        <td><StatusPill status={row.status} /></td>
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

function groupRelations(edges: EntityEdge[]) {
  const groups = new Map<
    string,
    {
      key: string;
      sourceNodeId: string;
      targetNodeId: string;
      relation: string;
      count: number;
      confidence: number;
      status: EntityEdge["status"];
      sources: Set<string>;
    }
  >();

  for (const edge of edges) {
    const key = `${edge.source_node_id}:${edge.relation}:${edge.target_node_id}`;
    const existing = groups.get(key);
    if (existing) {
      existing.count += 1;
      existing.confidence = Math.max(existing.confidence, edge.confidence);
      if (edge.source_id) existing.sources.add(edge.source_id);
      continue;
    }
    groups.set(key, {
      key,
      sourceNodeId: edge.source_node_id,
      targetNodeId: edge.target_node_id,
      relation: edge.relation,
      count: 1,
      confidence: edge.confidence,
      status: edge.status,
      sources: new Set(edge.source_id ? [edge.source_id] : []),
    });
  }

  return [...groups.values()].sort((a, b) => {
    if (a.relation !== b.relation) return a.relation.localeCompare(b.relation);
    if (a.sourceNodeId !== b.sourceNodeId) return a.sourceNodeId.localeCompare(b.sourceNodeId);
    return a.targetNodeId.localeCompare(b.targetNodeId);
  });
}

function nodeLabel(node?: EntityNode) {
  if (!node) return "Missing node";
  return `${node.canonical_name} (${node.type})`;
}
