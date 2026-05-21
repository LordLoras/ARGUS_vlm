import { useRef, useEffect, useCallback, useState, useImperativeHandle, forwardRef } from "react";
import ForceGraph3D from "react-force-graph-3d";
import SpriteText from "three-spritetext";
import * as THREE from "three";
import type { GraphData, GraphNode, GraphLink, NodeType } from "./types";
import { NODE_TYPE_COLORS, NODE_TYPE_SIZES } from "./types";

export interface GraphCanvasHandle {
  projectToScreen: (x: number, y: number, z: number) => { x: number; y: number } | null;
  getCanvasRect: () => DOMRect | null;
}

interface Props {
  graphData: GraphData;
  selectedNodeId: string | null;
  onNodeClick: (node: GraphNode) => void;
  hoveredNodeId: string | null;
  onNodeHover: (node: GraphNode | null) => void;
}

export const GraphCanvas = forwardRef<GraphCanvasHandle, Props>(function GraphCanvas(
  { graphData, selectedNodeId, onNodeClick, hoveredNodeId, onNodeHover },
  ref
) {
  const fgRef = useRef<any>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useImperativeHandle(ref, () => ({
    projectToScreen(x: number, y: number, z: number) {
      const fg = fgRef.current;
      if (!fg) return null;
      const coords = fg.graph2ScreenCoords(x, y, z);
      if (!coords || !isFinite(coords.x) || !isFinite(coords.y)) return null;
      return { x: coords.x, y: coords.y };
    },
    getCanvasRect() {
      return wrapRef.current?.getBoundingClientRect() ?? null;
    },
  }));

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-300);
    fg.d3Force("link")?.distance((link: any) => {
      const strength = link.strength ?? 0.5;
      return 80 + (1 - strength) * 60;
    });
  }, [graphData]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      const fg = fgRef.current;
      if (!fg) return;
      const camDistance = 140;
      const nodePos = { x: node.x ?? 0, y: node.y ?? 0, z: node.z ?? 0 };
      const camDir = { x: nodePos.x * 0.15, y: nodePos.y * 0.15 + camDistance * 0.55, z: camDistance };
      fg.cameraPosition(camDir, nodePos, 1400);
      onNodeClick(node);
    },
    [onNodeClick]
  );

  const nodeMap = useCallback(() => {
    const m = new Map<string, GraphNode>();
    for (const n of graphData.nodes) m.set(n.id, n);
    return m;
  }, [graphData.nodes]);

  const customNodeRenderer = useCallback(
    (node: GraphNode) => {
      const color = NODE_TYPE_COLORS[node.type];
      const isSelected = node.id === selectedNodeId;
      const isHovered = node.id === hoveredNodeId;
      const size = NODE_TYPE_SIZES[node.type] ?? 5;
      const radius = size * (isSelected ? 0.6 : isHovered ? 0.55 : 0.45);

      const group = new THREE.Group();

      const geometry = new THREE.SphereGeometry(radius, 24, 24);
      const material = new THREE.MeshStandardMaterial({
        color,
        emissive: new THREE.Color(color),
        emissiveIntensity: isSelected ? 0.8 : isHovered ? 0.5 : 0.25,
        transparent: true,
        opacity: isSelected ? 1.0 : isHovered ? 0.95 : 0.85,
        roughness: 0.35,
        metalness: 0.6,
      });
      const sphere = new THREE.Mesh(geometry, material);
      group.add(sphere);

      if (isSelected || isHovered) {
        const glowGeo = new THREE.SphereGeometry(radius * 1.6, 16, 16);
        const glowMat = new THREE.MeshBasicMaterial({
          color,
          transparent: true,
          opacity: isSelected ? 0.15 : 0.08,
          side: THREE.BackSide,
        });
        group.add(new THREE.Mesh(glowGeo, glowMat));
      }

      if (isSelected) {
        const ringGeo = new THREE.RingGeometry(radius * 1.5, radius * 1.85, 48);
        const ringMat = new THREE.MeshBasicMaterial({
          color: new THREE.Color(color).lerp(new THREE.Color("#ffffff"), 0.3),
          transparent: true,
          opacity: 0.5,
          side: THREE.DoubleSide,
        });
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.lookAt(0, 0, 0);
        group.add(ring);
      }

      const label = node.label;
      const labelTextSize = isSelected ? 3.0 : isHovered ? 2.7 : 2.3;
      const sprite = new SpriteText(label, labelTextSize, "#e8eaee");
      sprite.position.y = radius + 3.8;
      sprite.textHeight = labelTextSize;
      sprite.backgroundColor = isSelected
        ? "rgba(8,9,11,0.94)"
        : isHovered
        ? "rgba(8,9,11,0.90)"
        : "rgba(8,9,11,0.82)";
      sprite.padding = 1.6;
      sprite.borderRadius = 2.0;
      sprite.borderColor = isSelected
        ? color
        : "rgba(255,255,255,0.10)";
      sprite.borderWidth = isSelected ? 1.0 : 0.4;
      group.add(sprite);

      return group;
    },
    [selectedNodeId, hoveredNodeId]
  );

  const isLinkHighlighted = useCallback(
    (link: GraphLink) => {
      const src =
        typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
      const tgt =
        typeof link.target === "string" ? link.target : (link.target as GraphNode).id;
      return (
        src === selectedNodeId ||
        tgt === selectedNodeId ||
        src === hoveredNodeId ||
        tgt === hoveredNodeId
      );
    },
    [selectedNodeId, hoveredNodeId]
  );

  const getLinkColor = useCallback(
    (link: GraphLink) => {
      const highlighted = isLinkHighlighted(link);
      if (highlighted) {
        const srcId =
          typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
        const tgtId =
          typeof link.target === "string" ? link.target : (link.target as GraphNode).id;
        const activeId = srcId === selectedNodeId || srcId === hoveredNodeId ? srcId : tgtId;
        const activeNode = nodeMap().get(activeId);
        if (activeNode) {
          const c = new THREE.Color(NODE_TYPE_COLORS[activeNode.type]);
          return `#${c.getHexString()}`;
        }
        return "rgba(255,255,255,0.55)";
      }
      return "rgba(255,255,255,0.22)";
    },
    [isLinkHighlighted, nodeMap, selectedNodeId, hoveredNodeId]
  );

  const getLinkWidth = useCallback(
    (link: GraphLink) => {
      const highlighted = isLinkHighlighted(link);
      const strength = link.strength ?? 0.5;
      const base = 0.6 + strength * 1.2;
      return highlighted ? base * 2.0 : base;
    },
    [isLinkHighlighted]
  );

  const getLinkParticleWidth = useCallback(
    (link: GraphLink) => {
      const highlighted = isLinkHighlighted(link);
      return highlighted ? 3.5 : 1.8;
    },
    [isLinkHighlighted]
  );

  return (
    <div className="kg-canvas-wrap" ref={wrapRef}>
      <ForceGraph3D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={graphData}
        nodeId="id"
        nodeVal={(node: any) => NODE_TYPE_SIZES[node.type as NodeType] ?? 5}
        nodeColor={(node: any) => NODE_TYPE_COLORS[node.type as NodeType]}
        nodeThreeObject={customNodeRenderer}
        nodeThreeObjectExtend={false}
        onNodeClick={handleNodeClick}
        onNodeHover={(node: any) => onNodeHover(node ?? null)}
        onNodeDragEnd={(node: any) => {
          node.fx = node.x;
          node.fy = node.y;
          node.fz = node.z;
        }}
        linkColor={getLinkColor as any}
        linkWidth={getLinkWidth}
        linkDirectionalParticles={1}
        linkDirectionalParticleWidth={getLinkParticleWidth as any}
        linkDirectionalParticleSpeed={0.008}
        linkDirectionalArrowLength={0}
        linkCurvature={0}
        linkVisibility={true}
        backgroundColor="#08090b"
        warmupTicks={80}
        cooldownTicks={500}
        d3AlphaDecay={0.015}
        d3VelocityDecay={0.38}
        enableNodeDrag={true}
        controlType="orbit"
        showNavInfo={false}
      />
      <div className="kg-controls-hint">
        <span>Drag to rotate</span>
        <span className="kg-hint-sep" />
        <span>Scroll to zoom</span>
        <span className="kg-hint-sep" />
        <span>Click to explore</span>
      </div>
    </div>
  );
});