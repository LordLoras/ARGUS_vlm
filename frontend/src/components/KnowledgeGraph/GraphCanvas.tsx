import { useRef, useEffect, useCallback, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import SpriteText from "three-spritetext";
import * as THREE from "three";
import type { GraphData, GraphNode, GraphLink, NodeType } from "./types";
import { NODE_TYPE_COLORS, NODE_TYPE_SIZES } from "./types";

interface Props {
  graphData: GraphData;
  selectedNodeId: string | null;
  onNodeClick: (node: GraphNode) => void;
  hoveredNodeId: string | null;
  onNodeHover: (node: GraphNode | null) => void;
}

export function GraphCanvas({
  graphData,
  selectedNodeId,
  onNodeClick,
  hoveredNodeId,
  onNodeHover,
}: Props) {
  const fgRef = useRef<any>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

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
    fg.d3Force("charge")?.strength(-320);
    fg.d3Force("link")?.distance((link: any) => {
      const strength = link.strength ?? 0.5;
      return 55 + (1 - strength) * 70;
    });
  }, [graphData]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      const fg = fgRef.current;
      if (!fg) return;
      const distance = 90;
      const distRatio =
        1 + distance / Math.hypot(node.x ?? 0, node.y ?? 0, node.z ?? 0);
      fg.cameraPosition(
        {
          x: (node.x ?? 0) * distRatio,
          y: (node.y ?? 0) * distRatio,
          z: (node.z ?? 0) * distRatio,
        },
        node,
        1600
      );
      onNodeClick(node);
    },
    [onNodeClick]
  );

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
        emissiveIntensity: isSelected ? 1.0 : isHovered ? 0.6 : 0.3,
        transparent: true,
        opacity: isSelected ? 1.0 : isHovered ? 0.95 : 0.85,
        roughness: 0.3,
        metalness: 0.65,
      });
      const sphere = new THREE.Mesh(geometry, material);
      group.add(sphere);

      if (isSelected || isHovered) {
        const glowGeo = new THREE.SphereGeometry(radius * 1.6, 16, 16);
        const glowMat = new THREE.MeshBasicMaterial({
          color,
          transparent: true,
          opacity: isSelected ? 0.12 : 0.06,
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
        ? "rgba(10,12,16,0.92)"
        : isHovered
        ? "rgba(10,12,16,0.88)"
        : "rgba(10,12,16,0.78)";
      sprite.padding = 1.6;
      sprite.borderRadius = 2.0;
      sprite.borderColor = isSelected
        ? color
        : "rgba(255,255,255,0.08)";
      sprite.borderWidth = isSelected ? 1.0 : 0.4;
      group.add(sprite);

      return group;
    },
    [selectedNodeId, hoveredNodeId]
  );

  const getLinkColor = useCallback(
    (link: GraphLink) => {
      const src =
        typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
      const tgt =
        typeof link.target === "string" ? link.target : (link.target as GraphNode).id;
      const isLinked =
        src === selectedNodeId ||
        tgt === selectedNodeId ||
        src === hoveredNodeId ||
        tgt === hoveredNodeId;
      return isLinked ? "rgba(255,255,255,0.18)" : "rgba(255,255,255,0.04)";
    },
    [selectedNodeId, hoveredNodeId]
  );

  const getLinkWidth = useCallback(
    (link: GraphLink) => {
      const src =
        typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
      const tgt =
        typeof link.target === "string" ? link.target : (link.target as GraphNode).id;
      const isLinked =
        src === selectedNodeId ||
        tgt === selectedNodeId ||
        src === hoveredNodeId ||
        tgt === hoveredNodeId;
      const base = 0.35 + (link.strength ?? 0.5) * 0.7;
      return isLinked ? base * 2.2 : base;
    },
    [selectedNodeId, hoveredNodeId]
  );

  const getLinkParticleWidth = useCallback(
    (link: GraphLink) => {
      const src =
        typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
      const tgt =
        typeof link.target === "string" ? link.target : (link.target as GraphNode).id;
      const isLinked =
        src === selectedNodeId ||
        tgt === selectedNodeId ||
        src === hoveredNodeId ||
        tgt === hoveredNodeId;
      return isLinked ? 2.5 : 1.2;
    },
    [selectedNodeId, hoveredNodeId]
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
        linkDirectionalParticleSpeed={0.006}
        linkDirectionalArrowLength={0}
        linkCurvature={0.08}
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
}