import { useState, useEffect, useCallback, useMemo } from "react";
import type { CSSProperties } from "react";
import { Topbar } from "../components/Topbar";
import { ScatterCanvas } from "../components/EmbeddingSpace/ScatterCanvas";
import type { ScatterPoint } from "../components/EmbeddingSpace/ScatterCanvas";
import { api } from "../lib/api-client";
import { CloseIcon, SearchIcon, LayersIcon, SparkleIcon } from "../lib/icons";

const CATEGORY_PALETTE = [
  "#7c3aed", "#3b82f6", "#10b981", "#f59e0b", "#ef4444",
  "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#8b5cf6",
  "#14b8a6", "#e11d48", "#0ea5e9", "#a3e635", "#d946ef",
  "#6366f1", "#22d3ee", "#fb923c", "#facc15", "#34d399",
];

type EmbeddingType = "text" | "visual";
type ExplorerMode = "single" | "mirror";

interface ScatterResponse {
  points: ScatterPoint[];
  categories: string[];
  total: number;
  sampled: number;
  type: EmbeddingType;
  projection?: string;
}

const EMBEDDING_META: Record<EmbeddingType, {
  label: string;
  model: string;
  dims: string;
  source: string;
  territory: string;
  explanation: string;
}> = {
  text: {
    label: "MiniLM space",
    model: "MiniLM text vectors",
    dims: "384d",
    source: "Transcript + OCR language",
    territory: "Message territory",
    explanation: "Bubbles sit close together when ads use similar language, offers, claims, or calls to action.",
  },
  visual: {
    label: "SigLIP space",
    model: "SigLIP 2 visual vectors",
    dims: "768d",
    source: "Keyframe visual style",
    territory: "Creative territory",
    explanation: "Bubbles sit close together when ads share similar scenes, objects, layouts, or visual treatment.",
  },
};

function LoadingFallback() {
  return (
    <div className="kg-loading">
      <div className="kg-loading-orb">
        <span className="kg-loading-orb-inner" />
        <span className="kg-loading-orb-ring" />
      </div>
      <div className="kg-loading-text">
        <span className="kg-loading-title">Computing Embedding Space</span>
        <span className="kg-loading-sub">Projecting MiniLM / SigLIP vectors...</span>
      </div>
    </div>
  );
}

function ConfidenceRing({ value, color, size = 48 }: { value: number; color: string; size?: number }) {
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const filled = circ * value;
  return (
    <svg width={size} height={size} className="es-conf-ring">
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--bg-3)"
        strokeWidth="3"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${circ}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ filter: `drop-shadow(0 0 4px ${color}60)` }}
      />
      <text
        x={size / 2}
        y={size / 2}
        textAnchor="middle"
        dominantBaseline="central"
        fill={color}
        fontSize="11"
        fontFamily="var(--mono)"
        fontWeight="600"
      >
        {Math.round(value * 100)}
      </text>
    </svg>
  );
}

function HoverTooltip({
  point,
  color,
  position,
}: {
  point: ScatterPoint;
  color: string;
  position: { x: number; y: number } | null;
}) {
  return (
    <div
      className="es-hover-card"
      style={{
        "--es-hc": color,
        left: position ? Math.min(position.x + 18, window.innerWidth - 430) : 16,
        top: position ? Math.max(position.y - 12, 14) : 16,
      } as CSSProperties}
    >
      <div className="es-hover-header">
        <span className="es-hover-dot" style={{ background: color, boxShadow: `0 0 8px ${color}50` }} />
        <span className="es-hover-cat">{point.category}</span>
        <span className="es-hover-conf">{Math.round(point.confidence * 100)}%</span>
      </div>
      <div className="es-hover-label">{point.label}</div>
      {point.brand && <div className="es-hover-brand">{point.brand}</div>}
    </div>
  );
}

function projectionDistance(a: ScatterPoint, b: ScatterPoint) {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2);
}

function nearestPoints(point: ScatterPoint | null | undefined, points: ScatterPoint[], limit = 3) {
  if (!point) return [];
  return points
    .filter((candidate) => candidate.id !== point.id)
    .sort((a, b) => projectionDistance(point, a) - projectionDistance(point, b))
    .slice(0, limit);
}

function signalSplitLabel(delta: number | null) {
  if (delta == null) return "Select an ad";
  if (delta < 42) return "Aligned";
  if (delta < 82) return "Mixed signal";
  return "Divergent";
}

function signalSplitCopy(delta: number | null) {
  if (delta == null) return "Click a bubble in either map to compare where the same ad lands in language space and visual space.";
  if (delta < 42) return "The ad lands in a similar territory in both maps, so messaging and creative are reinforcing each other.";
  if (delta < 82) return "The ad shares some neighborhood structure, but the message and the visuals emphasize different signals.";
  return "The ad moves to a different territory between maps, which is useful for spotting ads that say one thing and show another.";
}

function formatPointCoords(point: ScatterPoint | null | undefined) {
  if (!point) return "not indexed";
  return `${point.x.toFixed(0)} / ${point.y.toFixed(0)} / ${point.z.toFixed(0)}`;
}

export function Embeddings() {
  const [data, setData] = useState<ScatterResponse | null>(null);
  const [viewMode, setViewMode] = useState<ExplorerMode>("single");
  const [mirrorData, setMirrorData] = useState<Record<EmbeddingType, ScatterResponse | null>>({
    text: null,
    visual: null,
  });
  const [mirrorLoading, setMirrorLoading] = useState(false);
  const [mirrorError, setMirrorError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [embedType, setEmbedType] = useState<EmbeddingType>("text");
  const [selectedSpace, setSelectedSpace] = useState<EmbeddingType>("text");
  const [selectedPoint, setSelectedPoint] = useState<ScatterPoint | null>(null);
  const [hoveredPoint, setHoveredPoint] = useState<ScatterPoint | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);
  const [activeCategories, setActiveCategories] = useState<Set<string>>(new Set());
  const [clusterAds, setClusterAds] = useState<ScatterPoint[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [detailOpen, setDetailOpen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const embeddingMeta = EMBEDDING_META[embedType];
  const detailMeta = EMBEDDING_META[viewMode === "mirror" ? selectedSpace : embedType];

  const categoriesForFilters = useMemo(() => {
    if (viewMode === "mirror") {
      return Array.from(new Set([
        ...(mirrorData.text?.categories ?? []),
        ...(mirrorData.visual?.categories ?? []),
      ])).sort();
    }
    return data?.categories ?? [];
  }, [data, mirrorData, viewMode]);

  const categoryColors = useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    categoriesForFilters.forEach((cat, i) => {
      map[cat] = CATEGORY_PALETTE[i % CATEGORY_PALETTE.length];
    });
    return map;
  }, [categoriesForFilters]);

  useEffect(() => {
    if (viewMode !== "single") return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDetailOpen(false);
    setSelectedPoint(null);
    setSelectedSpace(embedType);
    api
      .getEmbeddingsScatter(embedType)
      .then((res) => {
        if (cancelled) return;
        setData(res as ScatterResponse);
        setActiveCategories(new Set(res.categories));
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load embeddings");
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [embedType, reloadKey, viewMode]);

  useEffect(() => {
    if (viewMode !== "mirror") return;
    let cancelled = false;
    setMirrorLoading(true);
    setMirrorError(null);
    setDetailOpen(false);
    setSelectedPoint(null);
    setHoveredPoint(null);
    setHoverPos(null);

    Promise.all([
      api.getEmbeddingsScatter("text"),
      api.getEmbeddingsScatter("visual"),
    ])
      .then(([textRes, visualRes]) => {
        if (cancelled) return;
        const nextMirrorData = {
          text: textRes as ScatterResponse,
          visual: visualRes as ScatterResponse,
        };
        setMirrorData(nextMirrorData);
        setActiveCategories(new Set([
          ...nextMirrorData.text.categories,
          ...nextMirrorData.visual.categories,
        ]));
        setMirrorLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setMirrorError(err instanceof Error ? err.message : "Failed to load embedding mirror");
        setMirrorLoading(false);
      });
    return () => { cancelled = true; };
  }, [reloadKey, viewMode]);

  const filterPoints = useCallback((points: ScatterPoint[]) => {
    let pts = points.filter((p) => activeCategories.has(p.category));
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      pts = pts.filter(
        (p) =>
          p.label.toLowerCase().includes(q) ||
          p.brand.toLowerCase().includes(q) ||
          p.category.toLowerCase().includes(q) ||
          p.id.toLowerCase().includes(q)
      );
    }
    return pts;
  }, [activeCategories, searchQuery]);

  const visiblePoints = useMemo(() => {
    if (!data) return [];
    return filterPoints(data.points);
  }, [data, filterPoints]);

  const mirrorVisiblePoints = useMemo(() => ({
    text: mirrorData.text ? filterPoints(mirrorData.text.points) : [],
    visual: mirrorData.visual ? filterPoints(mirrorData.visual.points) : [],
  }), [filterPoints, mirrorData]);

  const mirrorPointMap = useMemo(() => {
    const map = new Map<string, ScatterPoint>();
    mirrorData.text?.points.forEach((point) => map.set(point.id, point));
    mirrorData.visual?.points.forEach((point) => {
      if (!map.has(point.id)) map.set(point.id, point);
    });
    return map;
  }, [mirrorData]);

  const mirrorVisibleIds = useMemo(() => new Set([
    ...mirrorVisiblePoints.text.map((point) => point.id),
    ...mirrorVisiblePoints.visual.map((point) => point.id),
  ]), [mirrorVisiblePoints]);

  const stats = useMemo(() => {
    if (viewMode === "mirror") {
      return {
        total: Math.max(mirrorData.text?.total ?? 0, mirrorData.visual?.total ?? 0),
        sampled: mirrorPointMap.size,
        categories: categoriesForFilters.length,
        visible: mirrorVisibleIds.size,
      };
    }
    if (!data) return { total: 0, sampled: 0, categories: 0, visible: 0 };
    return {
      total: data.total,
      sampled: data.sampled,
      categories: categoriesForFilters.length,
      visible: visiblePoints.length,
    };
  }, [categoriesForFilters.length, data, mirrorData, mirrorPointMap, mirrorVisibleIds, viewMode, visiblePoints]);

  const categoryCounts = useMemo(() => {
    const map = new Map<string, number>();
    const sourcePoints = viewMode === "mirror" ? Array.from(mirrorPointMap.values()) : data?.points ?? [];
    sourcePoints.forEach((p) => map.set(p.category, (map.get(p.category) || 0) + 1));
    return map;
  }, [data, mirrorPointMap, viewMode]);

  const updateClusterAds = useCallback((point: ScatterPoint, points: ScatterPoint[]) => {
    const nearby = points
      .filter((p) => p.category === point.category && p.id !== point.id)
      .sort((a, b) => projectionDistance(point, a) - projectionDistance(point, b))
      .slice(0, 20);
    setClusterAds(nearby);
  }, []);

  const handleSinglePointClick = useCallback(
    (point: ScatterPoint) => {
      setSelectedSpace(embedType);
      setSelectedPoint(point);
      setDetailOpen(true);
      updateClusterAds(point, data?.points ?? []);
    },
    [data, embedType, updateClusterAds]
  );

  const handleMirrorPointClick = useCallback(
    (point: ScatterPoint, type: EmbeddingType) => {
      setSelectedSpace(type);
      setSelectedPoint(point);
      setDetailOpen(true);
      updateClusterAds(point, mirrorData[type]?.points ?? []);
    },
    [mirrorData, updateClusterAds]
  );

  const handleClose = useCallback(() => {
    setDetailOpen(false);
    setHoveredPoint(null);
    setHoverPos(null);
    setTimeout(() => {
      setSelectedPoint(null);
      setClusterAds([]);
    }, 200);
  }, []);

  const toggleCategory = useCallback((cat: string) => {
    setActiveCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat) && next.size > 1) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }, []);

  const handleHover = useCallback((point: ScatterPoint | null, position?: { x: number; y: number }) => {
    setHoveredPoint(point);
    setHoverPos(point && position ? position : null);
  }, []);

  const selectedColor = selectedPoint
    ? categoryColors[selectedPoint.category] || "#7c3aed"
    : "#7c3aed";
  const isLoading = viewMode === "mirror" ? mirrorLoading : loading;
  const activeError = viewMode === "mirror" ? mirrorError : error;
  const selectedTextPoint = selectedPoint
    ? mirrorData.text?.points.find((point) => point.id === selectedPoint.id) ?? null
    : null;
  const selectedVisualPoint = selectedPoint
    ? mirrorData.visual?.points.find((point) => point.id === selectedPoint.id) ?? null
    : null;
  const mirrorDelta = selectedTextPoint && selectedVisualPoint
    ? projectionDistance(selectedTextPoint, selectedVisualPoint)
    : null;
  const textNeighbors = selectedTextPoint ? nearestPoints(selectedTextPoint, mirrorData.text?.points ?? []) : [];
  const visualNeighbors = selectedVisualPoint ? nearestPoints(selectedVisualPoint, mirrorData.visual?.points ?? []) : [];
  const selectedMirrorLabel = selectedPoint?.label || selectedPoint?.brand || "Select an ad";
  const mirrorAlignmentScore = mirrorDelta == null
    ? 0
    : Math.max(0, Math.min(100, Math.round(100 - mirrorDelta)));
  const selectedCategoryTotal = selectedPoint
    ? (viewMode === "mirror"
      ? Array.from(mirrorPointMap.values()).filter((point) => point.category === selectedPoint.category).length
      : data?.points.filter((point) => point.category === selectedPoint.category).length ?? 0)
    : 0;

  return (
    <>
      <Topbar
        crumbs={["Intelligence", "Embedding Space"]}
        actions={
          <div className="kg-topbar-stats">
            <span className="kg-top-stat">
              <SparkleIcon size={10} />
              {stats.visible} visible
            </span>
          </div>
        }
      />

      <div className="knowledge-graph-layout">
        {isLoading ? (
          <LoadingFallback />
        ) : activeError ? (
          <div className="page" style={{ padding: 32 }}>
            <div className="es-error">
              <span className="es-error-title">Failed to load embeddings</span>
              <span className="es-error-msg">{activeError}</span>
              <button
                className="es-error-retry"
                onClick={() => setReloadKey((key) => key + 1)}
              >
                Retry
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="kg-toolbar">
              <div className="kg-toolbar-row">
                <div className="es-toolbar-left">
                  <div className="es-mode-toggle">
                    <button
                      className={`es-mode-btn ${viewMode === "single" ? "is-active" : ""}`}
                      onClick={() => setViewMode("single")}
                    >
                      Explore
                    </button>
                    <button
                      className={`es-mode-btn ${viewMode === "mirror" ? "is-active" : ""}`}
                      onClick={() => setViewMode("mirror")}
                    >
                      Mirror
                    </button>
                  </div>

                  {viewMode === "single" ? (
                    <div className="es-type-toggle">
                      <button
                        className={`es-type-btn ${embedType === "text" ? "is-active" : ""}`}
                        onClick={() => setEmbedType("text")}
                      >
                        <LayersIcon size={12} />
                        <span>MiniLM</span>
                        <span className="es-type-dim">384d</span>
                      </button>
                      <button
                        className={`es-type-btn ${embedType === "visual" ? "is-active" : ""}`}
                        onClick={() => setEmbedType("visual")}
                      >
                        <LayersIcon size={12} />
                        <span>SigLIP</span>
                        <span className="es-type-dim">768d</span>
                      </button>
                    </div>
                  ) : (
                    <div className="es-mirror-pill">
                      <LayersIcon size={12} />
                      <span>MiniLM</span>
                      <b>vs</b>
                      <span>SigLIP</span>
                    </div>
                  )}
                </div>

                <div className="kg-toolbar-actions">
                  <div className="kg-search-wrap" style={{ width: 220 }}>
                    <SearchIcon size={12} className="kg-search-icon" />
                    <input
                      className="kg-search-input"
                      type="text"
                      placeholder="Filter points..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                    />
                    {searchQuery && (
                      <button className="kg-search-clear" onClick={() => setSearchQuery("")}>
                        clear
                      </button>
                    )}
                  </div>
                </div>
              </div>

              <div className="kg-type-filters es-filter-row">
                {categoriesForFilters.map((cat) => (
                  <button
                    key={cat}
                    className={`kg-type-filter ${activeCategories.has(cat) ? "is-active" : ""}`}
                    onClick={() => toggleCategory(cat)}
                    style={{ "--type-color": categoryColors[cat] || "#7c3aed" } as CSSProperties}
                  >
                    <span className="kg-type-filter-dot" />
                    <span>{cat}</span>
                    <span className="es-cat-count">
                      {categoryCounts.get(cat) || 0}
                    </span>
                  </button>
                ))}
                <div className="kg-visible-count">
                  {stats.visible}/{stats.sampled} visible
                </div>
              </div>
            </div>

            <div className="es-canvas-area">
              {viewMode === "single" ? (
                <>
                  <ScatterCanvas
                    points={visiblePoints}
                    selectedId={selectedPoint?.id ?? null}
                    onPointClick={handleSinglePointClick}
                    onBackgroundClick={handleClose}
                    hoveredId={hoveredPoint?.id ?? null}
                    onPointHover={handleHover}
                    categoryColors={categoryColors}
                    activeCategories={activeCategories}
                  />

                  <div className="es-map-panel">
                    <div className="es-map-panel-head">
                      <span className="es-map-kicker">Ad similarity map</span>
                      <strong>{embeddingMeta.territory}</strong>
                      <p>{embeddingMeta.explanation}</p>
                    </div>
                    <div className="es-map-reading">
                      <span><b>Bubble</b> one ad</span>
                      <span><b>Near</b> similar</span>
                      <span><b>Color</b> category</span>
                    </div>
                    <div className="es-map-grid">
                      <span><b>{stats.sampled}</b> sampled</span>
                      <span><b>{stats.visible}</b> visible</span>
                      <span><b>{stats.categories}</b> categories</span>
                      <span><b>{embeddingMeta.dims}</b> dims</span>
                    </div>
                    <div className="es-map-source">{embeddingMeta.source}</div>
                  </div>

                  {visiblePoints.length === 0 && (
                    <div className="es-empty-overlay">
                      <span className="es-empty-title">No vectors in view</span>
                      <span className="es-empty-sub">Clear search or re-enable a category filter.</span>
                    </div>
                  )}

                  {hoveredPoint && !selectedPoint && (
                    <HoverTooltip
                      point={hoveredPoint}
                      color={categoryColors[hoveredPoint.category] || "#7c3aed"}
                      position={hoverPos}
                    />
                  )}
                </>
              ) : (
                <div className="es-mirror-stage">
                  <div className="es-mirror-pane is-text">
                    <div className="es-mirror-pane-head">
                      <span className="es-map-kicker">Message space</span>
                      <strong>MiniLM text map</strong>
                      <p>What the ad says: transcript, OCR, offers, claims, and calls to action.</p>
                      <em>{mirrorVisiblePoints.text.length} visible</em>
                    </div>
                    <div className="es-mirror-canvas">
                      <ScatterCanvas
                        compact
                        points={mirrorVisiblePoints.text}
                        selectedId={selectedPoint?.id ?? null}
                        onPointClick={(point) => handleMirrorPointClick(point, "text")}
                        onBackgroundClick={handleClose}
                        hoveredId={hoveredPoint?.id ?? null}
                        onPointHover={(point) => {
                          setHoveredPoint(point);
                          setHoverPos(null);
                        }}
                        categoryColors={categoryColors}
                        activeCategories={activeCategories}
                      />
                    </div>
                  </div>

                  <div className="es-mirror-bridge">
                    <span className="es-map-kicker">Dual-Embedding Mirror</span>
                    <strong>{selectedMirrorLabel}</strong>
                    <p>{signalSplitCopy(mirrorDelta)}</p>
                    <div
                      className={`es-mirror-signal is-${signalSplitLabel(mirrorDelta).toLowerCase().replace(/\s+/g, "-")}`}
                      style={{ "--type-color": selectedColor, "--alignment": `${mirrorAlignmentScore}%` } as CSSProperties}
                    >
                      <span>Signal read</span>
                      <b>{signalSplitLabel(mirrorDelta)}</b>
                      <em>{mirrorDelta == null ? "Click a bubble" : `${Math.round(mirrorDelta)} projection drift`}</em>
                      <div className="es-mirror-alignment">
                        <i />
                      </div>
                    </div>
                    <div className="es-mirror-vector-grid">
                      <div>
                        <span>Message position</span>
                        <strong>{formatPointCoords(selectedTextPoint)}</strong>
                      </div>
                      <div>
                        <span>Visual position</span>
                        <strong>{formatPointCoords(selectedVisualPoint)}</strong>
                      </div>
                    </div>
                    {selectedPoint ? (
                      <div
                        className="es-mirror-profile"
                        style={{ "--type-color": selectedColor } as CSSProperties}
                      >
                        <div className="es-mirror-profile-head">
                          <ConfidenceRing value={selectedPoint.confidence} color={selectedColor} size={42} />
                          <div>
                            <span>Selected ad</span>
                            <strong>{selectedPoint.label}</strong>
                            <em>{selectedSpace === "text" ? "Selected from message map" : "Selected from creative map"}</em>
                          </div>
                          <button className="es-detail-close" onClick={handleClose} aria-label="Close selected ad">
                            <CloseIcon size={14} />
                          </button>
                        </div>

                        <div className="es-mirror-metrics">
                          <div>
                            <span>Confidence</span>
                            <strong>{Math.round(selectedPoint.confidence * 100)}%</strong>
                          </div>
                          <div>
                            <span>Similar</span>
                            <strong>{clusterAds.length}</strong>
                          </div>
                          <div>
                            <span>Category set</span>
                            <strong>{selectedCategoryTotal}</strong>
                          </div>
                        </div>

                        <div className="es-mirror-meta">
                          {selectedPoint.brand && (
                            <div>
                              <span>Brand</span>
                              <strong>{selectedPoint.brand}</strong>
                            </div>
                          )}
                          <div>
                            <span>Category</span>
                            <strong>{selectedPoint.category}</strong>
                          </div>
                          <div>
                            <span>Ad ID</span>
                            <strong>{selectedPoint.id}</strong>
                          </div>
                        </div>

                        <div className="es-mirror-model-strip">
                          <div>
                            <span>Message model</span>
                            <strong>MiniLM 384d</strong>
                          </div>
                          <div>
                            <span>Creative model</span>
                            <strong>SigLIP 768d</strong>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="es-mirror-profile is-empty">
                        <span>Presentation cue</span>
                        <strong>Pick one ad to show the multimodal split.</strong>
                        <p>The same ad is highlighted in both spaces, making it easy to explain whether the language and the visuals tell the same story.</p>
                      </div>
                    )}
                    <div className="es-mirror-neighbors">
                      <div>
                        <span>Nearby in message</span>
                        {textNeighbors.length ? textNeighbors.map((point) => (
                          <button
                            key={point.id}
                            onClick={() => handleMirrorPointClick(point, "text")}
                            style={{ "--type-color": categoryColors[point.category] || "#7c3aed" } as CSSProperties}
                          >
                            {point.label}
                          </button>
                        )) : <small>Select an ad</small>}
                      </div>
                      <div>
                        <span>Nearby in creative</span>
                        {visualNeighbors.length ? visualNeighbors.map((point) => (
                          <button
                            key={point.id}
                            onClick={() => handleMirrorPointClick(point, "visual")}
                            style={{ "--type-color": categoryColors[point.category] || "#7c3aed" } as CSSProperties}
                          >
                            {point.label}
                          </button>
                        )) : <small>Select an ad</small>}
                      </div>
                    </div>
                  </div>

                  <div className="es-mirror-pane is-visual">
                    <div className="es-mirror-pane-head">
                      <span className="es-map-kicker">Creative space</span>
                      <strong>SigLIP visual map</strong>
                      <p>What the ad shows: scenes, objects, layouts, people, products, and visual style.</p>
                      <em>{mirrorVisiblePoints.visual.length} visible</em>
                    </div>
                    <div className="es-mirror-canvas">
                      <ScatterCanvas
                        compact
                        points={mirrorVisiblePoints.visual}
                        selectedId={selectedPoint?.id ?? null}
                        onPointClick={(point) => handleMirrorPointClick(point, "visual")}
                        onBackgroundClick={handleClose}
                        hoveredId={hoveredPoint?.id ?? null}
                        onPointHover={(point) => {
                          setHoveredPoint(point);
                          setHoverPos(null);
                        }}
                        categoryColors={categoryColors}
                        activeCategories={activeCategories}
                      />
                    </div>
                  </div>

                  {mirrorVisibleIds.size === 0 && (
                    <div className="es-empty-overlay">
                      <span className="es-empty-title">No vectors in either mirror</span>
                      <span className="es-empty-sub">Clear search or re-enable a category filter.</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Detail panel */}
            {selectedPoint && viewMode === "single" && (
              <div className={`es-detail ${detailOpen ? "is-open" : ""}`}>
                <div className="es-detail-header">
                  <div className="es-detail-header-left">
                    <ConfidenceRing value={selectedPoint.confidence} color={selectedColor} size={44} />
                    <div className="es-detail-title-col">
                      <h2 className="es-detail-title">{selectedPoint.label}</h2>
                      <div className="es-detail-subtitle">
                        <span
                          className="es-detail-badge"
                          style={{
                            color: selectedColor,
                            borderColor: `${selectedColor}40`,
                            background: `${selectedColor}15`,
                          }}
                        >
                          {selectedPoint.category}
                        </span>
                        <span className="es-detail-dim">
                          {Math.round(selectedPoint.confidence * 100)}% confidence
                        </span>
                      </div>
                    </div>
                  </div>
                  <button className="es-detail-close" onClick={handleClose} aria-label="Close">
                    <CloseIcon size={14} />
                  </button>
                </div>

                <div className="es-detail-body">
                  <div className="es-detail-metrics">
                    <div className="es-metric-card">
                      <span className="es-metric-value" style={{ color: selectedColor }}>
                        {Math.round(selectedPoint.confidence * 100)}%
                      </span>
                      <span className="es-metric-label">Confidence</span>
                      <div className="es-metric-bar">
                        <div
                          className="es-metric-bar-fill"
                          style={{
                            width: `${selectedPoint.confidence * 100}%`,
                            background: `linear-gradient(90deg, ${selectedColor}, ${selectedColor}aa)`,
                          }}
                        />
                      </div>
                    </div>
                    <div className="es-metric-card">
                      <span className="es-metric-value">{clusterAds.length}</span>
                      <span className="es-metric-label">Similar Ads</span>
                    </div>
                    <div className="es-metric-card">
                      <span className="es-metric-value">
                        {selectedCategoryTotal}
                      </span>
                      <span className="es-metric-label">Category Total</span>
                    </div>
                    <div className="es-metric-card">
                      <span className="es-metric-value">{detailMeta.dims}</span>
                      <span className="es-metric-label">Dimensions</span>
                    </div>
                  </div>

                  <div className="es-vector-strip">
                    <div>
                      <span>Model</span>
                      <strong>{detailMeta.territory}</strong>
                    </div>
                    <div>
                      <span>P1</span>
                      <strong>{selectedPoint.x.toFixed(1)}</strong>
                    </div>
                    <div>
                      <span>P2</span>
                      <strong>{selectedPoint.y.toFixed(1)}</strong>
                    </div>
                    <div>
                      <span>P3</span>
                      <strong>{selectedPoint.z.toFixed(1)}</strong>
                    </div>
                  </div>

                  <div className="es-detail-meta">
                    {selectedPoint.brand && (
                      <div className="es-meta-item">
                        <span className="es-meta-icon" style={{ background: `${selectedColor}18`, color: selectedColor }}>B</span>
                        <div>
                          <span className="es-meta-label">Brand</span>
                          <span className="es-meta-value">{selectedPoint.brand}</span>
                        </div>
                      </div>
                    )}
                    <div className="es-meta-item">
                      <span className="es-meta-icon" style={{ background: `${selectedColor}18`, color: selectedColor }}>C</span>
                      <div>
                        <span className="es-meta-label">Category</span>
                        <span className="es-meta-value">{selectedPoint.category}</span>
                      </div>
                    </div>
                    <div className="es-meta-item">
                      <span className="es-meta-icon" style={{ background: `${selectedColor}18`, color: selectedColor }}>I</span>
                      <div>
                        <span className="es-meta-label">Ad ID</span>
                        <span className="es-meta-value es-meta-mono">{selectedPoint.id}</span>
                      </div>
                    </div>
                  </div>

                  <div className="es-cluster-section">
                    <div className="es-cluster-header">
                      <span className="es-cluster-dot" style={{ background: selectedColor, boxShadow: `0 0 8px ${selectedColor}40` }} />
                      <span className="es-cluster-title" style={{ color: selectedColor }}>Most Similar Ads</span>
                      <span className="es-cluster-count">{clusterAds.length}</span>
                    </div>
                    <div className="es-cluster-items">
                      {clusterAds.slice(0, 10).map((p) => (
                        <button
                          key={p.id}
                          className="es-cluster-chip"
                          style={{
                            background: `${selectedColor}10`,
                            borderColor: `${selectedColor}30`,
                            color: selectedColor,
                          }}
                          onClick={() => handleSinglePointClick(p)}
                        >
                          <span className="es-cluster-chip-label">{p.label}</span>
                          <span className="es-cluster-chip-sub">{p.brand || p.id.slice(0, 8)}</span>
                        </button>
                      ))}
                      {clusterAds.length > 10 && (
                        <span className="es-cluster-more" style={{ color: selectedColor }}>
                          +{clusterAds.length - 10} more
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div className="kg-stats-bar">
              <div className="kg-stats-inner">
                <div className="kg-stat">
                  <span className="kg-stat-value">{stats.total}</span>
                  <span className="kg-stat-label">Total Ads</span>
                </div>
                <div className="kg-stat-divider" />
                <div className="kg-stat">
                  <span className="kg-stat-value">{stats.visible}</span>
                  <span className="kg-stat-label">Visible</span>
                </div>
                <div className="kg-stat-divider" />
                <div className="kg-stat">
                  <span className="kg-stat-value">{stats.categories}</span>
                  <span className="kg-stat-label">Categories</span>
                </div>
                <div className="kg-stat-divider" />
                <div className="kg-stat">
                  <span className="kg-stat-value">{viewMode === "mirror" ? "384d + 768d" : embeddingMeta.dims}</span>
                  <span className="kg-stat-label">Dimensions</span>
                </div>
                <div className="kg-stat-divider" />
                <div className="kg-stat kg-stat-accent">
                  <SparkleIcon size={9} />
                  <span className="kg-stat-value">{viewMode === "mirror" ? "Dual mirror" : embeddingMeta.label}</span>
                  <span className="kg-stat-label">Active Space</span>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
