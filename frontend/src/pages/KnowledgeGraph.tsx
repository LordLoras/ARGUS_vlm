import { useState, useEffect, useCallback, Suspense, lazy, useMemo, useRef } from "react";
import type { CSSProperties } from "react";
import { Topbar } from "../components/Topbar";
import { graphService } from "../components/KnowledgeGraph/graphService";
import type { GraphData, GraphLink, GraphNode } from "../components/KnowledgeGraph/types";
import { NODE_TYPE_COLORS, NODE_TYPE_LABELS } from "../components/KnowledgeGraph/types";

const CubeCanvas = lazy(() =>
  import("../components/CubeGraph/CubeCanvas").then((m) => ({ default: m.CubeCanvas }))
);
import { ChevronRightIcon, CloseIcon, FlowIcon, LayersIcon, PlayIcon } from "../lib/icons";
import { SparkleIcon, SearchIcon } from "../lib/icons";
import { FACE_COLORS } from "../components/CubeGraph/types";
import type { NodeType as CubeNodeType } from "../components/CubeGraph/types";

const FACE_GROUPS: { key: CubeNodeType; label: string; color: string }[] = [
  { key: "brand", label: "Brands", color: FACE_COLORS.brand },
  { key: "company", label: "Companies", color: FACE_COLORS.company },
  { key: "category", label: "Categories", color: FACE_COLORS.category },
  { key: "product", label: "Products", color: FACE_COLORS.product },
  { key: "subsidiary", label: "Subsidiaries", color: FACE_COLORS.subsidiary },
  { key: "future", label: "Future Signals", color: FACE_COLORS.future },
  { key: "research", label: "Research Briefs", color: FACE_COLORS.research },
];

const EMPTY_NODE_ID_SET = new Set<string>();
const ALL_NODE_TYPES = FACE_GROUPS.map((group) => group.key);

const DEMO_STORY: { id: string; title: string; subtitle: string }[] = [
  { id: "automotive", title: "Industry Map", subtitle: "OEMs, brands, products" },
  { id: "electric-vehicle", title: "EV Shift", subtitle: "Category pressure" },
  { id: "future-ev-price-compression", title: "Pricing Signal", subtitle: "Forward edge" },
  { id: "research-ev-incentives", title: "Agentic Brief", subtitle: "Deep research path" },
];

type DetailConnection = {
  node: GraphNode;
  label: string;
  strength: number;
  direction: "in" | "out";
};

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
  const [activeTypes, setActiveTypes] = useState<Set<CubeNodeType>>(() => new Set(ALL_NODE_TYPES));
  const [neighborhoodOnly, setNeighborhoodOnly] = useState(false);
  const [demoRunning, setDemoRunning] = useState(false);
  const [demoStepIndex, setDemoStepIndex] = useState<number | null>(null);
  const [recentExpansion, setRecentExpansion] = useState<{ sourceId: string; nodeIds: Set<string> } | null>(null);
  const expandingNodeIds = useRef(new Set<string>());
  const demoStepRef = useRef<number | null>(null);
  const graphNodesRef = useRef<GraphNode[]>([]);
  const handleNavigateRef = useRef<(node: GraphNode) => void>(() => undefined);

  useEffect(() => {
    let cancelled = false;
    graphService.getInitialGraph().then((res) => {
      if (cancelled) return;
      setGraphData({ nodes: res.nodes, links: res.links });
      setInitialLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!recentExpansion) return;
    const timer = window.setTimeout(() => setRecentExpansion(null), 2800);
    return () => window.clearTimeout(timer);
  }, [recentExpansion]);

  const handleNodeClick = useCallback(
    async (node: GraphNode) => {
      setSelectedNode(node);
      if (expandedNodeIds.has(node.id) || expandingNodeIds.current.has(node.id)) return;
      expandingNodeIds.current.add(node.id);
      setActiveExpansion(node);
      try {
        const result = await graphService.expandNode(node.id);
        if (result.new_nodes.length > 0 || result.new_links.length > 0) {
          const existingIds = new Set(graphNodesRef.current.map((existing) => existing.id));
          const addedNodeIds = result.new_nodes.filter((incoming) => !existingIds.has(incoming.id)).map((incoming) => incoming.id);
          setGraphData((prev) => ({
            nodes: mergeUnique(prev.nodes, seedExpansionNodes(result.new_nodes, node)),
            links: mergeUniqueLinks(prev.links, result.new_links),
          }));
          if (addedNodeIds.length > 0) {
            setRecentExpansion({ sourceId: node.id, nodeIds: new Set(addedNodeIds) });
          }
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
      setActiveTypes((prev) => {
        if (prev.has(node.type as CubeNodeType)) return prev;
        return new Set([...prev, node.type as CubeNodeType]);
      });
      setSelectedNode(node);
      if (!expandedNodeIds.has(node.id)) handleNodeClick(node);
    },
    [expandedNodeIds, handleNodeClick]
  );

  useEffect(() => {
    graphNodesRef.current = graphData.nodes;
  }, [graphData.nodes]);

  useEffect(() => {
    handleNavigateRef.current = handleNavigate;
  }, [handleNavigate]);

  const handleClose = useCallback(() => setSelectedNode(null), []);

  const nodeMap = useMemo(() => new Map(graphData.nodes.map((n) => [n.id, n])), [graphData.nodes]);

  const visibleGraphData = useMemo(() => {
    const includedIds = new Set<string>();
    const selectedId = selectedNode?.id ?? null;

    if (neighborhoodOnly && selectedId) {
      includedIds.add(selectedId);
      for (const link of graphData.links) {
        const src = endpointId(link.source);
        const tgt = endpointId(link.target);
        if (src === selectedId) includedIds.add(tgt);
        else if (tgt === selectedId) includedIds.add(src);
      }
    }

    const nodes = graphData.nodes.filter((node) => {
      const passesType = activeTypes.has(node.type as CubeNodeType);
      if (node.id === selectedId) return true;
      if (neighborhoodOnly && selectedId) return includedIds.has(node.id) && passesType;
      return passesType;
    });
    const visibleIds = new Set(nodes.map((node) => node.id));
    const links = graphData.links.filter((link) => visibleIds.has(endpointId(link.source)) && visibleIds.has(endpointId(link.target)));
    return { nodes, links };
  }, [graphData, activeTypes, neighborhoodOnly, selectedNode?.id]);

  const toggleNodeType = useCallback((type: CubeNodeType) => {
    setActiveTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type) && next.size > 1) next.delete(type);
      else next.add(type);
      return next;
    });
  }, []);

  const showAllTypes = useCallback(() => {
    setActiveTypes(new Set(ALL_NODE_TYPES));
  }, []);

  const handleRunDemo = useCallback(() => {
    setActiveTypes(new Set(ALL_NODE_TYPES));
    setNeighborhoodOnly(false);
    setSearchQuery("");
    demoStepRef.current = null;
    setDemoStepIndex(0);
    setDemoRunning(true);
  }, []);

  const handleStopDemo = useCallback(() => {
    setDemoRunning(false);
    setDemoStepIndex(null);
    demoStepRef.current = null;
  }, []);

  useEffect(() => {
    if (!demoRunning || demoStepIndex == null || initialLoading) return;
    if (demoStepRef.current === demoStepIndex) return;
    demoStepRef.current = demoStepIndex;

    const step = DEMO_STORY[demoStepIndex];
    const node = graphNodesRef.current.find((n) => n.id === step.id);
    if (node) handleNavigateRef.current(node);

    const timer = window.setTimeout(() => {
      if (demoStepIndex >= DEMO_STORY.length - 1) {
        setDemoRunning(false);
        return;
      }
      setDemoStepIndex((current) => (current == null ? 0 : Math.min(current + 1, DEMO_STORY.length - 1)));
    }, demoStepIndex >= DEMO_STORY.length - 1 ? 2200 : 3000);

    return () => window.clearTimeout(timer);
  }, [demoRunning, demoStepIndex, initialLoading]);

  useEffect(() => {
    if (demoRunning) return;
    demoStepRef.current = null;
  }, [demoRunning]);

  const filteredNodes = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase();
    return graphData.nodes.filter(
      (n) => n.label.toLowerCase().includes(q) || n.type.toLowerCase().includes(q) || (n.description && n.description.toLowerCase().includes(q))
    );
  }, [searchQuery, graphData.nodes]);

  const connectionDetails = useMemo<DetailConnection[]>(() => {
    if (!selectedNode) return [];
    const result: DetailConnection[] = [];
    for (const link of graphData.links) {
      const src = endpointId(link.source);
      const tgt = endpointId(link.target);
      if (src === selectedNode.id) {
        const target = nodeMap.get(tgt);
        if (target) result.push({ node: target, label: link.label ?? "related", strength: link.strength ?? 0.5, direction: "out" });
      } else if (tgt === selectedNode.id) {
        const source = nodeMap.get(src);
        if (source) result.push({ node: source, label: link.label ?? "related", strength: link.strength ?? 0.5, direction: "in" });
      }
    }
    return result;
  }, [selectedNode, graphData.links, nodeMap]);

  const connectionsByType = useMemo(() => {
    const result: Record<string, DetailConnection[]> = { brand: [], company: [], category: [], product: [], subsidiary: [], future: [], research: [] };
    for (const connection of connectionDetails) {
      const type = connection.node.type as CubeNodeType;
      if (!result[type].some((existing) => existing.node.id === connection.node.id && existing.label === connection.label)) {
        result[type].push(connection);
      }
    }
    return result;
  }, [connectionDetails]);

  const relationshipSummary = useMemo(() => {
    const counts = new Map<string, { count: number; strength: number }>();
    for (const connection of connectionDetails) {
      const current = counts.get(connection.label) ?? { count: 0, strength: 0 };
      current.count += 1;
      current.strength += connection.strength;
      counts.set(connection.label, current);
    }
    return [...counts.entries()]
      .map(([label, value]) => ({ label, count: value.count, strength: value.strength / value.count }))
      .sort((a, b) => b.count - a.count || b.strength - a.strength);
  }, [connectionDetails]);

  const totalConnections = connectionDetails.length;
  const color = selectedNode ? NODE_TYPE_COLORS[selectedNode.type] : "#7c3aed";
  const averageStrength = totalConnections
    ? Math.round((connectionDetails.reduce((sum, connection) => sum + connection.strength, 0) / totalConnections) * 100)
    : 0;
  const downstreamCount = connectionDetails.filter((connection) => connection.direction === "out").length;
  const firstResearchConnection = connectionDetails.find((connection) => connection.node.type === "research")?.node ?? null;
  const stats = {
    nodes: visibleGraphData.nodes.length,
    links: visibleGraphData.links.length,
    expansions: expandedNodeIds.size,
    horizon: graphData.nodes.filter((n) => n.type === "future" || n.type === "research").length,
  };
  const isAgenticNode = selectedNode?.type === "future" || selectedNode?.type === "research";

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
              <div className="kg-toolbar-row">
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

                <div className="kg-toolbar-actions">
                  <button
                    className={`kg-tool-button ${demoRunning ? "is-active" : ""}`}
                    onClick={demoRunning ? handleStopDemo : handleRunDemo}
                  >
                    <PlayIcon size={11} />
                    <span>{demoRunning ? "Running Story" : "Run Demo"}</span>
                  </button>
                  <button
                    className={`kg-tool-button ${neighborhoodOnly ? "is-active" : ""}`}
                    onClick={() => setNeighborhoodOnly((current) => !current)}
                    disabled={!selectedNode}
                  >
                    <FlowIcon size={12} />
                    <span>Neighborhood</span>
                  </button>
                  <button className="kg-tool-icon-button" onClick={showAllTypes} aria-label="Show all graph types">
                    <LayersIcon size={12} />
                  </button>
                </div>
              </div>

              <div className="kg-story-rail">
                {DEMO_STORY.map((step, index) => (
                  <button
                    key={step.id}
                    className={`kg-story-step ${demoStepIndex === index ? "is-active" : ""}`}
                    onClick={() => {
                      handleStopDemo();
                      setDemoStepIndex(index);
                      const node = graphData.nodes.find((n) => n.id === step.id);
                      if (node) handleNavigate(node);
                    }}
                  >
                    <span className="kg-story-index">{index + 1}</span>
                    <span className="kg-story-copy">
                      <span className="kg-story-title">{step.title}</span>
                      <span className="kg-story-subtitle">{step.subtitle}</span>
                    </span>
                  </button>
                ))}
              </div>

              <div className="kg-type-filters">
                {FACE_GROUPS.map((group) => (
                  <button
                    key={group.key}
                    className={`kg-type-filter ${activeTypes.has(group.key) ? "is-active" : ""}`}
                    onClick={() => toggleNodeType(group.key)}
                    style={{ "--type-color": group.color } as CSSProperties}
                  >
                    <span className="kg-type-filter-dot" />
                    <span>{group.label}</span>
                  </button>
                ))}
                <div className="kg-visible-count">
                  {stats.nodes}/{graphData.nodes.length} visible
                </div>
              </div>
            </div>

            <Suspense fallback={<LoadingFallback />}>
              <CubeCanvas
                graphData={visibleGraphData}
                selectedNodeId={selectedNode?.id ?? null}
                onNodeClick={handleNodeClick}
                onBackgroundClick={handleClose}
                hoveredNodeId={hoveredNode?.id ?? null}
                onNodeHover={handleNodeHover}
                newNodeIds={recentExpansion?.nodeIds ?? EMPTY_NODE_ID_SET}
                expandingFromId={recentExpansion?.sourceId ?? null}
              />
            </Suspense>

            {selectedNode && (
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

                  <div className="cg-detail-metrics">
                    <div className="cg-detail-metric">
                      <span className="cg-detail-metric-value">{totalConnections}</span>
                      <span className="cg-detail-metric-label">Links</span>
                    </div>
                    <div className="cg-detail-metric">
                      <span className="cg-detail-metric-value">{relationshipSummary.length}</span>
                      <span className="cg-detail-metric-label">Edge Types</span>
                    </div>
                    <div className="cg-detail-metric">
                      <span className="cg-detail-metric-value">{averageStrength}</span>
                      <span className="cg-detail-metric-label">Signal</span>
                    </div>
                    <div className="cg-detail-metric">
                      <span className="cg-detail-metric-value">{downstreamCount}</span>
                      <span className="cg-detail-metric-label">Outbound</span>
                    </div>
                  </div>

                  {isAgenticNode && (
                    <div className="cg-detail-agentic" style={{ borderColor: `${color}55`, background: `${color}12` }}>
                      <span className="cg-detail-agentic-label" style={{ color }}>Agentic research edge</span>
                      <span className="cg-detail-agentic-text">
                        Deep research can follow this node to assemble competitor ads, launch timing, claim language, category movement, and evidence-backed next questions.
                      </span>
                      <button
                        className="cg-detail-agentic-action"
                        style={{ color, borderColor: `${color}55`, background: `${color}14` }}
                        onClick={() => firstResearchConnection ? handleNavigate(firstResearchConnection) : setNeighborhoodOnly(true)}
                      >
                        {firstResearchConnection ? "Open linked brief" : "Focus evidence path"}
                        <ChevronRightIcon size={9} />
                      </button>
                    </div>
                  )}

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

                  {relationshipSummary.length > 0 && (
                    <div className="cg-edge-lanes">
                      <div className="cg-section-header">
                        <span>Relationship Lanes</span>
                        <span>{relationshipSummary.length}</span>
                      </div>
                      <div className="cg-edge-lane-list">
                        {relationshipSummary.slice(0, 6).map((item) => (
                          <div key={item.label} className="cg-edge-lane">
                            <span className="cg-edge-lane-label">{formatRelationshipLabel(item.label)}</span>
                            <span className="cg-edge-lane-bar">
                              <span style={{ width: `${Math.max(18, Math.min(100, item.strength * 100))}%`, background: color }} />
                            </span>
                            <span className="cg-edge-lane-count">{item.count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="cg-face-grid">
                    {FACE_GROUPS.map(({ key, label, color: groupColor }) => {
                      const items = connectionsByType[key] || [];
                      if (items.length === 0) return null;
                      return (
                        <div key={key} className="cg-face-card" style={{ borderColor: `${groupColor}50` }}>
                          <div className="cg-face-card-header">
                            <span className="cg-face-card-dot" style={{ background: groupColor }} />
                            <span className="cg-face-card-label" style={{ color: groupColor }}>{label}</span>
                            <span className="cg-face-card-count" style={{ color: groupColor }}>{items.length}</span>
                          </div>
                          <div className="cg-face-card-items">
                            {items.slice(0, 7).map(({ node: n, label: edgeLabel, strength }) => (
                              <button
                                key={`${n.id}-${edgeLabel}`}
                                className="cg-face-chip"
                                style={{ background: `${groupColor}15`, borderColor: `${groupColor}35`, color: groupColor }}
                                onMouseEnter={() => setHoveredNode(n)}
                                onMouseLeave={() => setHoveredNode(null)}
                                onFocus={() => setHoveredNode(n)}
                                onBlur={() => setHoveredNode(null)}
                                onClick={() => handleNavigate(n)}
                              >
                                <span className="cg-face-chip-label">{n.label}</span>
                                <span className="cg-face-chip-edge">{formatRelationshipLabel(edgeLabel)}</span>
                                <span className="cg-face-chip-strength" style={{ width: `${Math.max(14, strength * 28)}px`, background: groupColor }} />
                                <ChevronRightIcon size={7} className="cg-chip-chevron" />
                              </button>
                            ))}
                            {items.length > 7 && (
                              <span className="cg-face-more" style={{ color: groupColor }}>
                                +{items.length - 7} more
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
                <div className="kg-stat">
                  <span className="kg-stat-value">{stats.horizon}</span>
                  <span className="kg-stat-label">Horizon</span>
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

function formatRelationshipLabel(label?: string): string {
  return (label ?? "related")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
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
