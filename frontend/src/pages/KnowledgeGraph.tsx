import { useState, useEffect, useCallback, Suspense, lazy, useMemo, useRef } from "react";
import { Topbar } from "../components/Topbar";
import { graphService } from "../components/KnowledgeGraph/graphService";
import type { GraphData, GraphLink, GraphNode } from "../components/KnowledgeGraph/types";
import { NODE_TYPE_COLORS, NODE_TYPE_LABELS } from "../components/KnowledgeGraph/types";

const CubeCanvas = lazy(() =>
  import("../components/CubeGraph/CubeCanvas").then((m) => ({ default: m.CubeCanvas }))
);
import { ChevronRightIcon, CloseIcon } from "../lib/icons";
import { SparkleIcon, SearchIcon } from "../lib/icons";
import { FACE_COLORS } from "../components/CubeGraph/types";
import type { NodeType as CubeNodeType } from "../components/CubeGraph/types";

const FACE_GROUPS: { key: CubeNodeType; label: string; color: string }[] = [
  { key: "brand", label: "Brands", color: FACE_COLORS.brand },
  { key: "company", label: "Companies", color: FACE_COLORS.company },
  { key: "category", label: "Categories", color: FACE_COLORS.category },
  { key: "product", label: "Products", color: FACE_COLORS.product },
  { key: "subsidiary", label: "Subsidiaries", color: FACE_COLORS.subsidiary },
];

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
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set());
  const [activeExpansion, setActiveExpansion] = useState<GraphNode | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);
  const expandingNodeIds = useRef(new Set<string>());

  useEffect(() => {
    let cancelled = false;
    graphService.getInitialGraph().then((res) => {
      if (cancelled) return;
      setGraphData({ nodes: res.nodes, links: res.links });
      setInitialLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  const handleNodeClick = useCallback(
    async (node: GraphNode) => {
      setSelectedNode(node);
      if (expandedNodeIds.has(node.id) || expandingNodeIds.current.has(node.id)) return;
      expandingNodeIds.current.add(node.id);
      setActiveExpansion(node);
      try {
        const result = await graphService.expandNode(node.id);
        if (result.new_nodes.length > 0 || result.new_links.length > 0) {
          setGraphData((prev) => ({
            nodes: mergeUnique(prev.nodes, seedExpansionNodes(result.new_nodes, node)),
            links: mergeUniqueLinks(prev.links, result.new_links),
          }));
        }
        setExpandedNodeIds((prev) => new Set([...prev, node.id]));
      } finally {
        expandingNodeIds.current.delete(node.id);
        setActiveExpansion((current) => (current?.id === node.id ? null : current));
      }
    },
    [expandedNodeIds]
  );

  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node);
  }, []);

  const handleNavigate = useCallback(
    (node: GraphNode) => {
      setSelectedNode(node);
      if (!expandedNodeIds.has(node.id)) handleNodeClick(node);
    },
    [expandedNodeIds, handleNodeClick]
  );

  const handleClose = useCallback(() => setSelectedNode(null), []);

  const filteredNodes = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    return graphData.nodes.filter(
      (n) => n.label.toLowerCase().includes(q) || n.type.toLowerCase().includes(q) || (n.description && n.description.toLowerCase().includes(q))
    );
  }, [searchQuery, graphData.nodes]);

  const connByType = useMemo(() => {
    if (!selectedNode) return null;
    const nodeMap = new Map(graphData.nodes.map((n) => [n.id, n]));
    const result: Record<string, GraphNode[]> = { brand: [], company: [], category: [], product: [], subsidiary: [] };
    for (const link of graphData.links) {
      const src = endpointId(link.source);
      const tgt = endpointId(link.target);
      const addNode = (n: GraphNode) => {
        const t = n.type as CubeNodeType;
        if (result[t] && !result[t].some((existing) => existing.id === n.id)) result[t].push(n);
      };
      if (src === selectedNode.id) { const t = nodeMap.get(tgt); if (t) addNode(t); }
      else if (tgt === selectedNode.id) { const s = nodeMap.get(src); if (s) addNode(s); }
    }
    return result;
  }, [selectedNode, graphData]);

  const totalConnections = connByType ? Object.values(connByType).flat().length : 0;
  const color = selectedNode ? NODE_TYPE_COLORS[selectedNode.type] : "#7c3aed";
  const stats = { nodes: graphData.nodes.length, links: graphData.links.length, expansions: expandedNodeIds.size };

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
                  <button className="kg-search-clear" onClick={() => setSearchQuery("")} aria-label="Clear graph search">
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
                      onClick={() => { handleNavigate(n); setSearchQuery(""); }}
                    >
                      <span className="kg-search-result-dot" style={{ background: NODE_TYPE_COLORS[n.type] }} />
                      <span className="kg-search-result-label">{n.label}</span>
                      <span className="kg-search-result-type">{NODE_TYPE_LABELS[n.type]}</span>
                    </button>
                  ))}
                  {filteredNodes.length > 8 && (
                    <div className="kg-search-more">+{filteredNodes.length - 8} more matches</div>
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
              <CubeCanvas
                graphData={graphData}
                selectedNodeId={selectedNode?.id ?? null}
                onNodeClick={handleNodeClick}
                onBackgroundClick={handleClose}
                hoveredNodeId={hoveredNode?.id ?? null}
                onNodeHover={handleNodeHover}
              />
            </Suspense>

            {selectedNode && connByType && (
              <div className="cg-detail">
                <div className="cg-detail-head">
                  <div className="cg-detail-title-area">
                    <span className="cg-detail-dot" style={{ background: color, boxShadow: `0 0 12px ${color}60` }} />
                    <div className="cg-detail-title-col">
                      <h2 className="cg-detail-title">{selectedNode.label}</h2>
                      <div className="cg-detail-subtitle">
                        <span className="cg-detail-type-badge" style={{ color, borderColor: `${color}40`, background: `${color}15` }}>
                          {NODE_TYPE_LABELS[selectedNode.type]}
                        </span>
                        <span className="cg-detail-conn-count">{totalConnections} connections</span>
                      </div>
                    </div>
                  </div>
                  <button className="cg-detail-close" onClick={handleClose} aria-label="Close node details">
                    <CloseIcon size={14} />
                  </button>
                </div>

                <div className="cg-detail-body">
                  {selectedNode.description && <p className="cg-detail-desc">{selectedNode.description}</p>}

                  <div className="cg-detail-meta-grid">
                    {selectedNode.headquarters && (
                      <div className="cg-detail-meta-item">
                        <span className="cg-detail-meta-icon" style={{ background: `${color}20`, color }}>H</span>
                        <div>
                          <span className="cg-detail-meta-label">Headquarters</span>
                          <span className="cg-detail-meta-val">{selectedNode.headquarters}</span>
                        </div>
                      </div>
                    )}
                    {selectedNode.founded && (
                      <div className="cg-detail-meta-item">
                        <span className="cg-detail-meta-icon" style={{ background: `${color}20`, color }}>E</span>
                        <div>
                          <span className="cg-detail-meta-label">Founded</span>
                          <span className="cg-detail-meta-val">{selectedNode.founded}</span>
                        </div>
                      </div>
                    )}
                    {selectedNode.website && (
                      <div className="cg-detail-meta-item">
                        <span className="cg-detail-meta-icon" style={{ background: `${color}20`, color }}>W</span>
                        <div>
                          <span className="cg-detail-meta-label">Website</span>
                          <span className="cg-detail-meta-val">{selectedNode.website}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  {expandedNodeIds.has(selectedNode.id) && (
                    <div className="cg-detail-explored">
                      <span className="kg-expanded-pulse" />
                      Connections explored
                    </div>
                  )}

                  <div className="cg-face-grid">
                    {FACE_GROUPS.map(({ key, label, color: groupColor }) => {
                      const items = connByType[key] || [];
                      if (items.length === 0) return null;
                      return (
                        <div key={key} className="cg-face-card" style={{ borderColor: `${groupColor}50` }}>
                          <div className="cg-face-card-header">
                            <span className="cg-face-card-dot" style={{ background: groupColor }} />
                            <span className="cg-face-card-label" style={{ color: groupColor }}>{label}</span>
                            <span className="cg-face-card-count" style={{ color: groupColor }}>{items.length}</span>
                          </div>
                          <div className="cg-face-card-items">
                            {items.slice(0, 6).map((n) => (
                              <button
                                key={n.id}
                                className="cg-face-chip"
                                style={{ background: `${groupColor}15`, borderColor: `${groupColor}35`, color: groupColor }}
                                onClick={() => handleNavigate(n)}
                              >
                                {n.label}
                                <ChevronRightIcon size={7} className="cg-chip-chevron" />
                              </button>
                            ))}
                            {items.length > 6 && (
                              <span className="cg-face-more" style={{ color: groupColor }}>
                                +{items.length - 6} more
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {activeExpansion && (
              <div className="kg-expand-overlay">
                <div className="kg-expand-card">
                  <div className="kg-expand-orb-wrap">
                    <span className="kg-expand-orb" />
                    <span className="kg-expand-orb-ring" />
                    <span className="kg-expand-orb-ring-outer" />
                  </div>
                  <div className="kg-expand-text">
                    <span className="kg-expand-title">Searching knowledge base</span>
                    <span className="kg-expand-sub">Exploring connections for <strong>{activeExpansion.label}</strong></span>
                  </div>
                  <div className="kg-expand-bar"><div className="kg-expand-bar-fill" /></div>
                </div>
              </div>
            )}

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
  existing: GraphLink[],
  incoming: GraphLink[]
): GraphLink[] {
  const keys = new Set(
    existing.map((l) => {
      return linkKey(l);
    })
  );
  return [
    ...existing,
    ...incoming.filter((l) => {
      const key = linkKey(l);
      if (keys.has(key)) return false;
      keys.add(key);
      return true;
    }),
  ];
}

function endpointId(endpoint: string | GraphNode): string {
  return typeof endpoint === "string" ? endpoint : endpoint.id;
}

function linkKey(link: GraphLink): string {
  return `${endpointId(link.source)}:${link.label ?? ""}:${endpointId(link.target)}`;
}

function seedExpansionNodes(nodes: GraphNode[], source: GraphNode): GraphNode[] {
  if (nodes.length === 0) return nodes;
  const origin = {
    x: source.x ?? 0,
    y: source.y ?? 0,
    z: source.z ?? 0,
  };
  const radius = 24 + Math.min(nodes.length, 8) * 2;
  return nodes.map((node, index) => {
    if (node.x != null && node.y != null && node.z != null) return node;
    const angle = (index / nodes.length) * Math.PI * 2;
    const vertical = ((index % 3) - 1) * 10;
    return {
      ...node,
      x: origin.x + Math.cos(angle) * radius,
      y: origin.y + vertical,
      z: origin.z + Math.sin(angle) * radius,
    };
  });
}
