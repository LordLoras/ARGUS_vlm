import { useState, useEffect, useCallback, Suspense, lazy, useMemo } from "react";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { graphService } from "../components/KnowledgeGraph/graphService";
import type { GraphData, GraphNode, GraphMeta, NodeType } from "../components/KnowledgeGraph/types";
import { NODE_TYPE_COLORS, NODE_TYPE_LABELS } from "../components/KnowledgeGraph/types";

const GraphCanvas = lazy(() =>
  import("../components/KnowledgeGraph/GraphCanvas").then((m) => ({ default: m.GraphCanvas }))
);
const NodeDetail = lazy(() =>
  import("../components/KnowledgeGraph/NodeDetail").then((m) => ({ default: m.NodeDetail }))
);
import { ExpandAnimation } from "../components/KnowledgeGraph/ExpandAnimation";
import { SparkleIcon, SearchIcon } from "../lib/icons";

function Legend() {
  return (
    <div className="kg-legend">
      <div className="kg-legend-title">Node Types</div>
      {(Object.keys(NODE_TYPE_COLORS) as NodeType[]).map((type) => (
        <div key={type} className="kg-legend-item">
          <span className="kg-legend-dot" style={{ background: NODE_TYPE_COLORS[type] }} />
          <span>{NODE_TYPE_LABELS[type]}</span>
        </div>
      ))}
    </div>
  );
}

function LoadingFallback() {
  return (
    <div className="kg-loading">
      <div className="kg-loading-orb">
        <span className="kg-loading-orb-inner" />
        <span className="kg-loading-orb-ring" />
      </div>
      <div className="kg-loading-text">
        <span className="kg-loading-title">Initializing Knowledge Graph</span>
        <span className="kg-loading-sub">Loading 3D visualization engine...</span>
      </div>
    </div>
  );
}

export function KnowledgeGraph() {
  const health = useApiHealth();
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set());
  const [isExpanding, setIsExpanding] = useState(false);
  const [meta, setMeta] = useState<GraphMeta | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);

  useEffect(() => {
    let cancelled = false;
    graphService.getInitialGraph().then((res) => {
      if (cancelled) return;
      setGraphData({ nodes: res.nodes, links: res.links });
      setMeta(res.meta);
      setInitialLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleNodeClick = useCallback(
    async (node: GraphNode) => {
      setSelectedNode(node);

      if (expandedNodeIds.has(node.id)) return;

      setIsExpanding(true);
      try {
        const result = await graphService.expandNode(node.id);
        if (result.new_nodes.length > 0) {
          setGraphData((prev) => ({
            nodes: mergeUnique(prev.nodes, result.new_nodes),
            links: mergeUniqueLinks(prev.links, result.new_links),
          }));
        }
        setExpandedNodeIds((prev) => new Set([...prev, node.id]));
      } finally {
        setIsExpanding(false);
      }
    },
    [expandedNodeIds]
  );

  const handleNavigate = useCallback(
    (node: GraphNode) => {
      setSelectedNode(node);
      if (!expandedNodeIds.has(node.id)) {
        handleNodeClick(node);
      }
    },
    [expandedNodeIds, handleNodeClick]
  );

  const handleClose = useCallback(() => setSelectedNode(null), []);

  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node);
  }, []);

  const filteredNodes = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    return graphData.nodes.filter(
      (n) =>
        n.label.toLowerCase().includes(q) ||
        n.type.toLowerCase().includes(q) ||
        (n.description && n.description.toLowerCase().includes(q))
    );
  }, [searchQuery, graphData.nodes]);

  const stats = {
    nodes: graphData.nodes.length,
    links: graphData.links.length,
    expansions: expandedNodeIds.size,
  };

  return (
    <>
      <Topbar
        crumbs={["Intelligence", "Knowledge Graph"]}
        actions={
          <div className="kg-topbar-stats">
            <span className="kg-top-stat">
              <SparkleIcon size={10} />
              {stats.expansions} explored
            </span>
          </div>
        }
      />

      <div className="knowledge-graph-layout">
        {initialLoading ? (
          <LoadingFallback />
        ) : (
          <>
            <div className="kg-toolbar">
              <div className="kg-search-wrap">
                <SearchIcon size={12} className="kg-search-icon" />
                <input
                  className="kg-search-input"
                  type="text"
                  placeholder="Search nodes..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onFocus={() => setSearchFocused(true)}
                  onBlur={() => setSearchFocused(false)}
                />
                {searchQuery && (
                  <button className="kg-search-clear" onClick={() => setSearchQuery("")}>
                    clear
                  </button>
                )}
              </div>
              {filteredNodes && filteredNodes.length > 0 && (
                <div className="kg-search-results">
                  {filteredNodes.slice(0, 8).map((n) => (
                    <button
                      key={n.id}
                      className="kg-search-result-item"
                      onClick={() => {
                        handleNavigate(n);
                        setSearchQuery("");
                      }}
                    >
                      <span
                        className="kg-search-result-dot"
                        style={{ background: NODE_TYPE_COLORS[n.type] }}
                      />
                      <span className="kg-search-result-label">{n.label}</span>
                      <span className="kg-search-result-type">{NODE_TYPE_LABELS[n.type]}</span>
                    </button>
                  ))}
                  {filteredNodes.length > 8 && (
                    <div className="kg-search-more">
                      +{filteredNodes.length - 8} more matches
                    </div>
                  )}
                </div>
              )}
              {filteredNodes !== null && filteredNodes.length === 0 && searchFocused && (
                <div className="kg-search-results">
                  <div className="kg-search-empty">No matching nodes found</div>
                </div>
              )}
            </div>

            <Suspense fallback={<LoadingFallback />}>
              <GraphCanvas
                graphData={graphData}
                selectedNodeId={selectedNode?.id ?? null}
                onNodeClick={handleNodeClick}
                hoveredNodeId={hoveredNode?.id ?? null}
                onNodeHover={handleNodeHover}
              />
            </Suspense>

            {selectedNode && (
              <Suspense fallback={null}>
                <NodeDetail
                  node={selectedNode}
                  graphData={graphData}
                  expanded={expandedNodeIds.has(selectedNode.id)}
                  onClose={handleClose}
                  onNavigate={handleNavigate}
                />
              </Suspense>
            )}

            {isExpanding && <ExpandAnimation label={selectedNode?.label ?? ""} />}

            <Legend />

            <div className="kg-stats-bar">
              <div className="kg-stats-inner">
                <div className="kg-stat">
                  <span className="kg-stat-value">{stats.nodes}</span>
                  <span className="kg-stat-label">Nodes</span>
                </div>
                <div className="kg-stat-divider" />
                <div className="kg-stat">
                  <span className="kg-stat-value">{stats.links}</span>
                  <span className="kg-stat-label">Connections</span>
                </div>
                <div className="kg-stat-divider" />
                <div className="kg-stat">
                  <span className="kg-stat-value">{stats.expansions}</span>
                  <span className="kg-stat-label">Explored</span>
                </div>
                <div className="kg-stat-divider" />
                <div className="kg-stat kg-stat-accent">
                  <SparkleIcon size={9} />
                  <span className="kg-stat-value">Ever-expanding</span>
                  <span className="kg-stat-label">Graph</span>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}

function mergeUnique(existing: GraphNode[], incoming: GraphNode[]): GraphNode[] {
  const ids = new Set(existing.map((n) => n.id));
  return [...existing, ...incoming.filter((n) => !ids.has(n.id))];
}

function mergeUniqueLinks(
  existing: { source: string | GraphNode; target: string | GraphNode; label?: string; strength?: number }[],
  incoming: { source: string | GraphNode; target: string | GraphNode; label?: string; strength?: number }[]
) {
  const keys = new Set(
    existing.map((l) => {
      const s = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
      const t = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
      return `${s}->${t}`;
    })
  );
  return [
    ...existing,
    ...incoming.filter((l) => {
      const s = typeof l.source === "string" ? l.source : (l.source as GraphNode).id;
      const t = typeof l.target === "string" ? l.target : (l.target as GraphNode).id;
      return !keys.has(`${s}->${t}`);
    }),
  ];
}