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
type ExplorerMode = "single" | "real3d";

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

function signalSplitLabel(delta: number | null) {
  if (delta == null) return "Select an ad";
  if (delta < 15) return "Aligned";
  if (delta < 35) return "Mixed";
  return "Divergent";
}

function signalSplitCopy(delta: number | null) {
  if (delta == null) return "Click a bubble in either map to compare where the same ad genuinely lands in text space and visual space — no artificial layout.";
  if (delta < 15) return "The ad lands close in both real spaces. Message and visuals are tightly correlated in the raw embeddings.";
  if (delta < 35) return "The ad shows some separation between what it says and how it looks — this is the honest distance between text and visual vectors.";
  return "The ad occupies meaningfully different regions in text vs visual space. The language and imagery tell different stories.";
}

function formatPointCoords(point: ScatterPoint | null | undefined) {
  if (!point) return "not indexed";
  return `${point.x.toFixed(0)} / ${point.y.toFixed(0)} / ${point.z.toFixed(0)}`;
}

export function Embeddings() {
  const [data, setData] = useState<ScatterResponse | null>(null);
  const [viewMode, setViewMode] = useState<ExplorerMode>("single");
  const [real3dData, setReal3dData] = useState<Record<EmbeddingType, ScatterResponse | null>>({
    text: null,
    visual: null,
  });
  const [real3dLoading, setReal3dLoading] = useState(false);
  const [real3dError, setReal3dError] = useState<string | null>(null);
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
  const detailMeta = EMBEDDING_META[viewMode === "real3d" ? selectedSpace : embedType];

  const categoriesForFilters = useMemo(() => {
    if (viewMode === "real3d") {
      return Array.from(new Set([
        ...(real3dData.text?.categories ?? []),
        ...(real3dData.visual?.categories ?? []),
      ])).sort();
    }
    return data?.categories ?? [];
  }, [data, real3dData, viewMode]);

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
    if (viewMode !== "real3d") return;
    let cancelled = false;
    setReal3dLoading(true);
    setReal3dError(null);
    setDetailOpen(false);
    setSelectedPoint(null);
    setHoveredPoint(null);
    setHoverPos(null);

    Promise.all([
      api.getEmbeddingsScatter("text", 600, "real"),
      api.getEmbeddingsScatter("visual", 600, "real"),
    ])
      .then(([textRes, visualRes]) => {
        if (cancelled) return;
        const next = {
          text: textRes as ScatterResponse,
          visual: visualRes as ScatterResponse,
        };
        setReal3dData(next);
        setActiveCategories(new Set([
          ...next.text.categories,
          ...next.visual.categories,
        ]));
        setReal3dLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setReal3dError(err instanceof Error ? err.message : "Failed to load embedding space");
        setReal3dLoading(false);
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

  const real3dVisiblePoints = useMemo(() => ({
    text: real3dData.text ? filterPoints(real3dData.text.points) : [],
    visual: real3dData.visual ? filterPoints(real3dData.visual.points) : [],
  }), [filterPoints, real3dData]);

  const real3dPointMap = useMemo(() => {
    const map = new Map<string, ScatterPoint>();
    real3dData.text?.points.forEach((point) => map.set(point.id, point));
    real3dData.visual?.points.forEach((point) => {
      if (!map.has(point.id)) map.set(point.id, point);
    });
    return map;
  }, [real3dData]);

  const real3dVisibleIds = useMemo(() => new Set([
    ...real3dVisiblePoints.text.map((point) => point.id),
    ...real3dVisiblePoints.visual.map((point) => point.id),
  ]), [real3dVisiblePoints]);

  const stats = useMemo(() => {
    if (viewMode === "real3d") {
      return {
        total: Math.max(real3dData.text?.total ?? 0, real3dData.visual?.total ?? 0),
        sampled: real3dPointMap.size,
        categories: categoriesForFilters.length,
        visible: real3dVisibleIds.size,
      };
    }
    if (!data) return { total: 0, sampled: 0, categories: 0, visible: 0 };
    return {
      total: data.total,
      sampled: data.sampled,
      categories: categoriesForFilters.length,
      visible: visiblePoints.length,
    };
  }, [categoriesForFilters.length, data, real3dData, real3dPointMap, real3dVisibleIds, viewMode, visiblePoints]);

  const categoryCounts = useMemo(() => {
    const map = new Map<string, number>();
    const sourcePoints = viewMode === "real3d" ? Array.from(real3dPointMap.values()) : data?.points ?? [];
    sourcePoints.forEach((p) => map.set(p.category, (map.get(p.category) || 0) + 1));
    return map;
  }, [data, real3dPointMap, viewMode]);

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

  const handleReal3dPointClick = useCallback(
    (point: ScatterPoint, type: EmbeddingType) => {
      setSelectedSpace(type);
      setSelectedPoint(point);
      setDetailOpen(true);
      updateClusterAds(point, real3dData[type]?.points ?? []);
    },
    [real3dData, updateClusterAds]
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
  const isLoading = viewMode === "real3d" ? real3dLoading : loading;
  const activeError = viewMode === "real3d" ? real3dError : error;
  const selectedTextPoint = selectedPoint
    ? real3dData.text?.points.find((point) => point.id === selectedPoint.id) ?? null
    : null;
  const selectedVisualPoint = selectedPoint
    ? real3dData.visual?.points.find((point) => point.id === selectedPoint.id) ?? null
    : null;
  const real3dDelta = selectedTextPoint && selectedVisualPoint
    ? projectionDistance(selectedTextPoint, selectedVisualPoint)
    : null;
  const selectedReal3dLabel = selectedPoint?.label || selectedPoint?.brand || "Select an ad";
  const real3dAlignmentScore = real3dDelta == null
    ? 0
    : Math.max(0, Math.min(100, Math.round(100 - real3dDelta)));
  const selectedCategoryTotal = selectedPoint
    ? (viewMode === "real3d"
      ? Array.from(real3dPointMap.values()).filter((point) => point.category === selectedPoint.category).length
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
                      className={`es-mode-btn ${viewMode === "real3d" ? "is-active" : ""}`}
                      onClick={() => setViewMode("real3d")}
                    >
                      Real 3D
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
                      <SparkleIcon size={12} />
                      <span>MiniLM</span>
                      <b>+</b>
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
                      <span className="es-map-kicker">Text PCA (real)</span>
                      <strong>MiniLM raw projection</strong>
                      <p>Actual 3D PCA of transcript + OCR embeddings. No category-guided layout. Points are where they genuinely land.</p>
                      <em>{real3dVisiblePoints.text.length} visible</em>
                    </div>
                    <div className="es-mirror-canvas">
                      <ScatterCanvas
                        compact
                        points={real3dVisiblePoints.text}
                        selectedId={selectedPoint?.id ?? null}
                        onPointClick={(point) => handleReal3dPointClick(point, "text")}
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
                    <span className="es-map-kicker">Real 3D PCA — No Layout Distortion</span>
                    <strong>{selectedReal3dLabel}</strong>
                    <p>{signalSplitCopy(real3dDelta)}</p>

                    {selectedPoint ? (
                      <div
                        className="es-mirror-profile"
                        style={{ "--type-color": selectedColor } as CSSProperties}
                      >
                        <div className="es-mirror-profile-head">
                          <ConfidenceRing value={selectedPoint.confidence} color={selectedColor} size={36} />
                          <div>
                            <strong>{selectedPoint.brand || selectedPoint.label}</strong>
                            <span>{selectedPoint.category.replace(/_/g, " ")}</span>
                          </div>
                          <button className="es-detail-close" onClick={handleClose} aria-label="Close">
                            <CloseIcon size={12} />
                          </button>
                        </div>

                        <div className={`es-mirror-signal is-${signalSplitLabel(real3dDelta).toLowerCase().replace(/\s+/g, "-")}`}
                          style={{ "--type-color": selectedColor, "--alignment": `${real3dAlignmentScore}%` } as CSSProperties}
                        >
                          <b>{signalSplitLabel(real3dDelta)}</b>
                          <em>{real3dDelta == null ? "Click a point" : `${Math.round(real3dDelta)} unit drift`}</em>
                          <div className="es-mirror-alignment"><i /></div>
                        </div>

                        <div className="es-mirror-metrics">
                          <div>
                            <span>Text</span>
                            <strong>{formatPointCoords(selectedTextPoint)}</strong>
                          </div>
                          <div>
                            <span>Visual</span>
                            <strong>{formatPointCoords(selectedVisualPoint)}</strong>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="es-mirror-profile is-empty">
                        <span>Unmodified PCA</span>
                        <strong>Click a point to inspect its position in both real embedding spaces.</strong>
                        <p>Positions show genuine PCA coordinates with no artificial category grouping.</p>
                      </div>
                    )}

                    {selectedPoint ? (
                      <>
                        {clusterAds.length > 0 && (
                          <div className="es-mirror-cluster">
                            <span className="es-mirror-cluster-head">Closest in same category</span>
                            <div className="es-mirror-cluster-chips">
                              {clusterAds.slice(0, 6).map((p) => (
                                <button
                                  key={p.id}
                                  onClick={() => handleReal3dPointClick(p, selectedSpace)}
                                  style={{ "--chip": categoryColors[p.category] || "#7c3aed" } as CSSProperties}
                                >
                                  <i />
                                  <span>{p.brand || p.label}</span>
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    ) : null}

                    <div className="es-mirror-reference">
                      <div className="es-ref-section">
                        <span className="es-ref-heading">Category legend</span>
                        <div className="es-ref-chips">
                          {categoriesForFilters.map((cat) => (
                            <span
                              key={cat}
                              className="es-ref-chip"
                              style={{ "--chip": categoryColors[cat] || "#7c3aed" } as CSSProperties}
                            >
                              <i />
                              {cat.replace(/_/g, " ")}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="es-ref-section">
                        <span className="es-ref-heading">Text-visual drift</span>
                        <div className="es-ref-drift-list">
                          <div className="es-ref-drift-row">
                            <span className="es-ref-tick is-aligned"><i />Aligned &lt;15</span>
                            <small>Same ad lands at similar coordinates in text and visual PCA — message and creative are reinforcing each other.</small>
                          </div>
                          <div className="es-ref-drift-row">
                            <span className="es-ref-tick is-mixed"><i />Mixed 15–35</span>
                            <small>Text and visual vectors place the ad in noticeably different regions — language and imagery emphasize different signals.</small>
                          </div>
                          <div className="es-ref-drift-row">
                            <span className="es-ref-tick is-divergent"><i />Divergent &gt;35</span>
                            <small>The ad occupies meaningfully different territory in each space — says one thing and shows another.</small>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="es-mirror-pane is-visual">
                    <div className="es-mirror-pane-head">
                      <span className="es-map-kicker">Visual PCA (real)</span>
                      <strong>SigLIP raw projection</strong>
                      <p>Actual 3D PCA of keyframe visual embeddings. Brand clusters emerge naturally — no artificial positioning.</p>
                      <em>{real3dVisiblePoints.visual.length} visible</em>
                    </div>
                    <div className="es-mirror-canvas">
                      <ScatterCanvas
                        compact
                        showCategoryLabels={false}
                        points={real3dVisiblePoints.visual}
                        selectedId={selectedPoint?.id ?? null}
                        onPointClick={(point) => handleReal3dPointClick(point, "visual")}
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

                  {real3dVisibleIds.size === 0 && (
                    <div className="es-empty-overlay">
                      <span className="es-empty-title">No vectors in either space</span>
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
                  <span className="kg-stat-value">{viewMode === "real3d" ? "384d + 768d" : embeddingMeta.dims}</span>
                  <span className="kg-stat-label">Dimensions</span>
                </div>
                <div className="kg-stat-divider" />
                <div className="kg-stat kg-stat-accent">
                  <SparkleIcon size={9} />
                  <span className="kg-stat-value">{viewMode === "real3d" ? "Real PCA" : embeddingMeta.label}</span>
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
