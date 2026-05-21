import { useEffect, useRef, useState, useCallback } from "react";
import { CloseIcon, ChevronRightIcon } from "../../lib/icons";
import type { GraphNode, GraphData } from "./types";
import { NODE_TYPE_COLORS, NODE_TYPE_LABELS } from "./types";
import type { GraphCanvasHandle } from "./GraphCanvas";

interface Props {
  node: GraphNode;
  graphData: GraphData;
  expanded: boolean;
  onClose: () => void;
  onNavigate: (node: GraphNode) => void;
  canvasHandle: GraphCanvasHandle | null;
}

export function NodeDetail({ node, graphData, expanded, onClose, onNavigate, canvasHandle }: Props) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef({ mx: 0, my: 0, ox: 0, oy: 0 });
  const posRef = useRef({ x: 0, y: 0 });
  const [visible, setVisible] = useState(false);

  const connections = getConnections(node.id, graphData);
  const color = NODE_TYPE_COLORS[node.type];
  const typeLabel = NODE_TYPE_LABELS[node.type];
  const incomingCount = connections.incoming.length;
  const outgoingCount = connections.outgoing.length;
  const totalConnections = incomingCount + outgoingCount;

  useEffect(() => {
    setDragOffset({ x: 0, y: 0 });
    setVisible(false);
  }, [node.id]);

  useEffect(() => {
    if (!canvasHandle || !node) return;
    let raf: number;

    const update = () => {
      const projected = canvasHandle.projectToScreen(node.x ?? 0, node.y ?? 0, node.z ?? 0);
      const rect = canvasHandle.getCanvasRect();
      if (!projected || !rect) {
        setVisible(false);
        raf = requestAnimationFrame(update);
        return;
      }

      const cardWidth = 340;
      const offsetX = 70;
      const offsetY = -16;
      let baseX = projected.x + offsetX;
      const baseY = projected.y + offsetY;

      if (baseX + cardWidth > rect.width - 12) {
        baseX = projected.x - cardWidth - offsetX;
      }
      const clampedY = Math.max(12, Math.min(baseY, rect.height - 300));

      posRef.current = { x: baseX, y: clampedY };
      if (cardRef.current) {
        cardRef.current.style.left = `${baseX + dragOffset.x}px`;
        cardRef.current.style.top = `${clampedY + dragOffset.y}px`;
      }
      setVisible(true);
      raf = requestAnimationFrame(update);
    };

    raf = requestAnimationFrame(update);
    return () => cancelAnimationFrame(raf);
  }, [canvasHandle, node, dragOffset]);

  const onDragStart = useCallback((e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest("button")) return;
    setDragging(true);
    dragStart.current = { mx: e.clientX, my: e.clientY, ox: dragOffset.x, oy: dragOffset.y };
    e.preventDefault();
  }, [dragOffset]);

  useEffect(() => {
    if (!dragging) return;
    const onMove = (e: PointerEvent) => {
      const dx = e.clientX - dragStart.current.mx;
      const dy = e.clientY - dragStart.current.my;
      setDragOffset({ x: dragStart.current.ox + dx, y: dragStart.current.oy + dy });
    };
    const onUp = () => setDragging(false);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [dragging]);

  if (!visible) return null;

  return (
    <div
      ref={cardRef}
      className={`kg-popup${dragging ? " kg-popup--dragging" : ""}`}
      style={{ left: posRef.current.x + dragOffset.x, top: posRef.current.y + dragOffset.y }}
      onPointerDown={onDragStart}
    >
      <div className="kg-popup-head">
        <div className="kg-popup-title-row">
          <span className="kg-popup-dot" style={{ background: color, boxShadow: `0 0 8px ${color}50` }} />
          <h3 className="kg-popup-title">{node.label}</h3>
          <span className="kg-popup-badge" style={{ color, borderColor: `${color}40`, background: `${color}15` }}>
            {typeLabel}
          </span>
        </div>
        <button className="kg-popup-close" onClick={onClose}>
          <CloseIcon size={11} />
        </button>
      </div>
      <div className="kg-popup-body">
        {node.description && <p className="kg-popup-desc">{node.description}</p>}

        <div className="kg-popup-meta">
          {node.industries && node.industries.length > 0 && (
            <div className="kg-popup-meta-row">
              <span className="kg-popup-meta-label">Industry</span>
              <span className="kg-popup-meta-val">{node.industries.join(", ")}</span>
            </div>
          )}
          {node.headquarters && (
            <div className="kg-popup-meta-row">
              <span className="kg-popup-meta-label">HQ</span>
              <span className="kg-popup-meta-val">{node.headquarters}</span>
            </div>
          )}
          {node.founded && (
            <div className="kg-popup-meta-row">
              <span className="kg-popup-meta-label">Founded</span>
              <span className="kg-popup-meta-val">{node.founded}</span>
            </div>
          )}
          {node.parentCompany && (
            <div className="kg-popup-meta-row">
              <span className="kg-popup-meta-label">Parent</span>
              <span className="kg-popup-meta-val">{node.parentCompany}</span>
            </div>
          )}
          {node.categories && node.categories.length > 0 && (
            <div className="kg-popup-meta-row">
              <span className="kg-popup-meta-label">Cat.</span>
              <span className="kg-popup-meta-val">{node.categories.join(", ")}</span>
            </div>
          )}
        </div>

        {expanded && (
          <div className="kg-popup-expanded">
            <span className="kg-expanded-pulse" />
            Connections explored
          </div>
        )}

        {totalConnections > 0 && (
          <div className="kg-popup-connections">
            <div className="kg-popup-conn-header">Connections ({totalConnections})</div>
            {outgoingCount > 0 && (
              <div className="kg-popup-conn-group">
                <div className="kg-popup-conn-group-label">Outgoing ({outgoingCount})</div>
                <div className="kg-popup-conn-list">
                  {connections.outgoing.map((conn) => {
                    const c = NODE_TYPE_COLORS[conn.node.type];
                    return (
                      <button key={`o-${conn.node.id}`} className="kg-popup-conn-item" onClick={() => onNavigate(conn.node)}>
                        <span className="kg-popup-conn-dot" style={{ background: c }} />
                        <span className="kg-popup-conn-label">{conn.node.label}</span>
                        {conn.linkLabel && <span className="kg-popup-conn-type">{conn.linkLabel}</span>}
                        <ChevronRightIcon size={8} className="kg-popup-conn-chevron" />
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {incomingCount > 0 && (
              <div className="kg-popup-conn-group">
                <div className="kg-popup-conn-group-label">Incoming ({incomingCount})</div>
                <div className="kg-popup-conn-list">
                  {connections.incoming.map((conn) => {
                    const c = NODE_TYPE_COLORS[conn.node.type];
                    return (
                      <button key={`i-${conn.node.id}`} className="kg-popup-conn-item" onClick={() => onNavigate(conn.node)}>
                        <span className="kg-popup-conn-dot" style={{ background: c }} />
                        <span className="kg-popup-conn-label">{conn.node.label}</span>
                        {conn.linkLabel && <span className="kg-popup-conn-type">{conn.linkLabel}</span>}
                        <ChevronRightIcon size={8} className="kg-popup-conn-chevron" />
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="kg-popup-drag-hint">drag to reposition</div>
    </div>
  );
}

interface ConnectionResult {
  incoming: { node: GraphNode; linkLabel?: string }[];
  outgoing: { node: GraphNode; linkLabel?: string }[];
}

function getConnections(nodeId: string, graphData: GraphData): ConnectionResult {
  const nodeMap = new Map(graphData.nodes.map((n) => [n.id, n]));
  const incoming: { node: GraphNode; linkLabel?: string }[] = [];
  const outgoing: { node: GraphNode; linkLabel?: string }[] = [];

  for (const link of graphData.links) {
    const src = typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
    const tgt = typeof link.target === "string" ? link.target : (link.target as GraphNode).id;

    if (src === nodeId) {
      const target = nodeMap.get(tgt);
      if (target) outgoing.push({ node: target, linkLabel: link.label });
    } else if (tgt === nodeId) {
      const source = nodeMap.get(src);
      if (source) incoming.push({ node: source, linkLabel: link.label });
    }
  }

  return { incoming, outgoing };
}