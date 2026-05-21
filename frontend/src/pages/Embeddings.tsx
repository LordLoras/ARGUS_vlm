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

interface ScatterResponse {
  points: ScatterPoint[];
  categories: string[];
  total: number;
  sampled: number;
  type: EmbeddingType;
  projection?: string;
}

const EMBEDDING_META: Record<EmbeddingType, { label: string; model: string; dims: string; source: string }> = {
  text: {
    label: "MiniLM space",
    model: "MiniLM text vectors",
    dims: "384d",
    source: "Transcript + OCR",
  },
  visual: {
    label: "SigLIP space",
    model: "SigLIP 2 visual vectors",
    dims: "768d",
    source: "Keyframe mean pool",
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

export function Embeddings() {
  const [data, setData] = useState<ScatterResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [embedType, setEmbedType] = useState<EmbeddingType>("text");
  const [selectedPoint, setSelectedPoint] = useState<ScatterPoint | null>(null);
  const [hoveredPoint, setHoveredPoint] = useState<ScatterPoint | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);
  const [activeCategories, setActiveCategories] = useState<Set<string>>(new Set());
  const [clusterAds, setClusterAds] = useState<ScatterPoint[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [detailOpen, setDetailOpen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const embeddingMeta = EMBEDDING_META[embedType];

  const categoryColors = useMemo<Record<string, string>>(() => {
    if (!data) return {};
    const map: Record<string, string> = {};
    data.categories.forEach((cat, i) => {
      map[cat] = CATEGORY_PALETTE[i % CATEGORY_PALETTE.length];
    });
    return map;
  }, [data]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDetailOpen(false);
    setSelectedPoint(null);
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
  }, [embedType, reloadKey]);

  const visiblePoints = useMemo(() => {
    if (!data) return [];
    let pts = data.points.filter((p) => activeCategories.has(p.category));
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
  }, [data, activeCategories, searchQuery]);

  const stats = useMemo(() => {
    if (!data) return { total: 0, sampled: 0, categories: 0, visible: 0 };
    return {
      total: data.total,
      sampled: data.sampled,
      categories: data.categories.length,
      visible: visiblePoints.length,
    };
  }, [data, visiblePoints]);

  const categoryCounts = useMemo(() => {
    if (!data) return new Map<string, number>();
    const map = new Map<string, number>();
    data.points.forEach((p) => map.set(p.category, (map.get(p.category) || 0) + 1));
    return map;
  }, [data]);

  const handlePointClick = useCallback(
    (point: ScatterPoint) => {
      setSelectedPoint(point);
      setDetailOpen(true);
      if (data) {
        const nearby = data.points
          .filter((p) => p.category === point.category && p.id !== point.id)
          .sort((a, b) => {
            const da = Math.sqrt((a.x - point.x) ** 2 + (a.y - point.y) ** 2 + (a.z - point.z) ** 2);
            const db = Math.sqrt((b.x - point.x) ** 2 + (b.y - point.y) ** 2 + (b.z - point.z) ** 2);
            return da - db;
          })
          .slice(0, 20);
        setClusterAds(nearby);
      }
    },
    [data]
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
        {loading ? (
          <LoadingFallback />
        ) : error ? (
          <div className="page" style={{ padding: 32 }}>
            <div className="es-error">
              <span className="es-error-title">Failed to load embeddings</span>
              <span className="es-error-msg">{error}</span>
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
                {data?.categories.map((cat) => (
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
              <ScatterCanvas
                points={visiblePoints}
                selectedId={selectedPoint?.id ?? null}
                onPointClick={handlePointClick}
                onBackgroundClick={handleClose}
                hoveredId={hoveredPoint?.id ?? null}
                onPointHover={handleHover}
                categoryColors={categoryColors}
                activeCategories={activeCategories}
              />

              <div className="es-map-panel">
                <div className="es-map-panel-head">
                  <span className="es-map-kicker">Guided projection</span>
                  <strong>{embeddingMeta.model}</strong>
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
            </div>

            {/* Detail panel */}
            {selectedPoint && (
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
                      <span className="es-metric-label">Cluster Size</span>
                    </div>
                    <div className="es-metric-card">
                      <span className="es-metric-value">
                        {data?.points.filter((p) => p.category === selectedPoint.category).length ?? 0}
                      </span>
                      <span className="es-metric-label">In Category</span>
                    </div>
                    <div className="es-metric-card">
                      <span className="es-metric-value">{embedType === "text" ? "384" : "768"}</span>
                      <span className="es-metric-label">Dimensions</span>
                    </div>
                  </div>

                  <div className="es-vector-strip">
                    <div>
                      <span>Model</span>
                      <strong>{embeddingMeta.model}</strong>
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
                      <span className="es-cluster-title" style={{ color: selectedColor }}>Nearest Cluster</span>
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
                          onClick={() => handlePointClick(p)}
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
                  <span className="kg-stat-value">{embedType === "text" ? "384d" : "768d"}</span>
                  <span className="kg-stat-label">Dimensions</span>
                </div>
                <div className="kg-stat-divider" />
                <div className="kg-stat kg-stat-accent">
                  <SparkleIcon size={9} />
                  <span className="kg-stat-value">{embeddingMeta.label}</span>
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
