import { useRef, useEffect, useCallback, useState, useMemo } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";
import type { GraphData, GraphNode, GraphLink, NodeType } from "./types";
import { NODE_TYPE_COLORS, NODE_TYPE_SIZES, FACE_COLORS, FACE_ORDER } from "./types";

interface Props {
  graphData: GraphData;
  selectedNodeId: string | null;
  onNodeClick: (node: GraphNode) => void;
  hoveredNodeId: string | null;
  onNodeHover: (node: GraphNode | null) => void;
}

function createFaceTexture(
  label: string,
  items: string[],
  faceColor: string,
  isTop: boolean
): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "#0c0e12";
  ctx.fillRect(0, 0, 256, 256);

  ctx.fillStyle = faceColor;
  ctx.globalAlpha = 0.25;
  ctx.fillRect(0, 0, 256, 256);
  ctx.globalAlpha = 1;

  ctx.strokeStyle = faceColor;
  ctx.globalAlpha = 0.5;
  ctx.lineWidth = 3;
  ctx.strokeRect(4, 4, 248, 248);
  ctx.globalAlpha = 1;

  if (isTop) {
    ctx.fillStyle = faceColor;
    ctx.font = "bold 22px Inter, system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, 128, 110, 230);

    ctx.font = "14px JetBrains Mono, monospace";
    ctx.globalAlpha = 0.6;
    ctx.fillText(FACE_ORDER.length + " face types", 128, 140);
    ctx.globalAlpha = 1;

    ctx.fillStyle = "#4a5060";
    ctx.font = "11px JetBrains Mono, monospace";
    ctx.fillText("Click to rotate", 128, 170);
  } else {
    ctx.fillStyle = faceColor;
    ctx.font = "bold 13px JetBrains Mono, monospace";
    ctx.textAlign = "left";
    ctx.fillText(label.toUpperCase(), 16, 28);

    ctx.strokeStyle = faceColor;
    ctx.globalAlpha = 0.3;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(16, 38);
    ctx.lineTo(240, 38);
    ctx.stroke();
    ctx.globalAlpha = 1;

    ctx.fillStyle = "#d4d8e0";
    ctx.font = "15px Inter, system-ui, sans-serif";
    const maxItems = 7;
    const displayItems = items.slice(0, maxItems);
    displayItems.forEach((item, i) => {
      ctx.fillText(item, 20, 60 + i * 28, 220);
    });

    if (items.length > maxItems) {
      ctx.fillStyle = "#6b7280";
      ctx.font = "12px JetBrains Mono, monospace";
      ctx.fillText(`+${items.length - maxItems} more`, 20, 60 + displayItems.length * 28);
    }

    if (items.length === 0) {
      ctx.fillStyle = "#4a5060";
      ctx.font = "13px Inter, system-ui, sans-serif";
      ctx.fillText("No connections", 20, 80);
    }
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  return tex;
}

function buildCubeMaterials(node: GraphNode, graphData: GraphData): THREE.Material[] {
  const connMap = buildConnectionMap(node.id, graphData);
  const color = NODE_TYPE_COLORS[node.type];

  const topTex = createFaceTexture(node.label, [], color, true);

  const bottomTex = createFaceTexture("info", [
    node.founded ? `Est. ${node.founded}` : "",
    node.headquarters ?? "",
    node.website ?? "",
  ].filter(Boolean), "#6b7280", false);

  const brandTex = createFaceTexture("Brands", connMap.brand, FACE_COLORS.brand, false);
  const companyTex = createFaceTexture("Companies", connMap.company, FACE_COLORS.company, false);
  const categoryTex = createFaceTexture("Categories", connMap.category, FACE_COLORS.category, false);
  const productTex = createFaceTexture("Products", connMap.product, FACE_COLORS.product, false);

  // THREE.BoxGeometry face order: +X, -X, +Y, -Y, +Z, -Z
  // We map: +X=brand, -X=subsidiary, +Y=top(label), -Y=bottom(info), +Z=company, -Z=category+product
  return [
    new THREE.MeshStandardMaterial({ map: brandTex, roughness: 0.4, metalness: 0.5 }),
    new THREE.MeshStandardMaterial({ map: productTex, roughness: 0.4, metalness: 0.5 }),
    new THREE.MeshStandardMaterial({ map: topTex, roughness: 0.3, metalness: 0.6 }),
    new THREE.MeshStandardMaterial({ map: bottomTex, roughness: 0.4, metalness: 0.5 }),
    new THREE.MeshStandardMaterial({ map: companyTex, roughness: 0.4, metalness: 0.5 }),
    new THREE.MeshStandardMaterial({ map: categoryTex, roughness: 0.4, metalness: 0.5 }),
  ];
}

interface ConnectionMap {
  brand: string[];
  company: string[];
  category: string[];
  product: string[];
  subsidiary: string[];
}

function buildConnectionMap(nodeId: string, graphData: GraphData): ConnectionMap {
  const nodeMap = new Map(graphData.nodes.map((n) => [n.id, n]));
  const result: ConnectionMap = { brand: [], company: [], category: [], product: [], subsidiary: [] };

  for (const link of graphData.links) {
    const src = typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
    const tgt = typeof link.target === "string" ? link.target : (link.target as GraphNode).id;

    if (src === nodeId) {
      const target = nodeMap.get(tgt);
      if (target) {
        const t = target.type as NodeType;
        if (result[t]) result[t].push(target.label);
      }
    } else if (tgt === nodeId) {
      const source = nodeMap.get(src);
      if (source) {
        const t = source.type as NodeType;
        if (result[t]) result[t].push(source.label);
      }
    }
  }

  return result;
}

const FACE_ROTATIONS: Record<string, { x: number; y: number }> = {
  brand: { x: 0, y: -Math.PI / 2 },
  product: { x: 0, y: Math.PI / 2 },
  company: { x: 0, y: 0 },
  category: { x: 0, y: Math.PI },
  info: { x: -Math.PI / 2, y: 0 },
  _top: { x: Math.PI / 2, y: 0 },
};

function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3);
}

export function CubeCanvas({
  graphData,
  selectedNodeId,
  onNodeClick,
  hoveredNodeId,
  onNodeHover,
}: Props) {
  const fgRef = useRef<any>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const cubeGroupRefs = useRef(new Map<string, THREE.Group>());
  const animFrame = useRef<number>(0);
  const cubeTextures = useRef(new Map<string, THREE.Material[]>());
  const prevDataKey = useRef<string>("");

  const dataKey = graphData.nodes.map((n) => n.id).join(",");

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({ width: entry.contentRect.width, height: entry.contentRect.height });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-280);
    fg.d3Force("link")?.distance((link: any) => {
      const strength = link.strength ?? 0.5;
      return 70 + (1 - strength) * 50;
    });
  }, [graphData]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      const fg = fgRef.current;
      if (!fg) return;
      const distance = 130;
      const distRatio = 1 + distance / Math.hypot(node.x ?? 0, node.y ?? 0, node.z ?? 0);
      fg.cameraPosition(
        { x: (node.x ?? 0) * distRatio, y: (node.y ?? 0) * distRatio, z: (node.z ?? 0) * distRatio },
        node,
        1400
      );
      onNodeClick(node);
    },
    [onNodeClick]
  );

  const customNodeRenderer = useCallback(
    (node: GraphNode) => {
      const isSelected = node.id === selectedNodeId;
      const isHovered = node.id === hoveredNodeId;
      const size = NODE_TYPE_SIZES[node.type] ?? 5;
      const cubeSize = size * (isSelected ? 1.8 : isHovered ? 1.5 : 1.2);

      const group = new THREE.Group();

      const geometry = new THREE.BoxGeometry(cubeSize, cubeSize, cubeSize);

      const key = node.id + "|" + dataKey;
      let materials: THREE.Material[];
      if (cubeTextures.current.has(key)) {
        materials = cubeTextures.current.get(key)!;
      } else {
        materials = buildCubeMaterials(node, graphData);
        cubeTextures.current.set(key, materials);
      }

      const mesh = new THREE.Mesh(geometry, materials);
      group.add(mesh);

      if (isSelected) {
        const edgesGeo = new THREE.EdgesGeometry(geometry);
        const edgesMat = new THREE.LineBasicMaterial({
          color: NODE_TYPE_COLORS[node.type],
          transparent: true,
          opacity: 0.8,
        });
        group.add(new THREE.LineSegments(edgesGeo, edgesMat));
      }

      if (isSelected || isHovered) {
        const glowGeo = new THREE.BoxGeometry(cubeSize * 1.25, cubeSize * 1.25, cubeSize * 1.25);
        const glowMat = new THREE.MeshBasicMaterial({
          color: NODE_TYPE_COLORS[node.type],
          transparent: true,
          opacity: isSelected ? 0.08 : 0.04,
          side: THREE.BackSide,
        });
        group.add(new THREE.Mesh(glowGeo, glowMat));
      }

      cubeGroupRefs.current.set(node.id, group);
      return group;
    },
    [selectedNodeId, hoveredNodeId, graphData, dataKey]
  );

  useEffect(() => {
    if (!selectedNodeId) return;

    const rotTarget = { x: 0, y: 0 };
    rotTarget.x = -0.4;
    rotTarget.y = 0.3;

    const group = cubeGroupRefs.current.get(selectedNodeId);
    if (group) {
      const startRot = { x: group.rotation.x, y: group.rotation.y };
      const startTime = performance.now();
      const duration = 800;

      const animate = () => {
        const elapsed = performance.now() - startTime;
        const t = Math.min(elapsed / duration, 1);
        const eased = easeOutCubic(t);
        group.rotation.x = startRot.x + (rotTarget.x - startRot.x) * eased;
        group.rotation.y = startRot.y + (rotTarget.y - startRot.y) * eased;
        if (t < 1) {
          animFrame.current = requestAnimationFrame(animate);
        }
      };
      cancelAnimationFrame(animFrame.current);
      animFrame.current = requestAnimationFrame(animate);
    }

    return () => cancelAnimationFrame(animFrame.current);
  }, [selectedNodeId]);

  const isLinkHighlighted = useCallback(
    (link: GraphLink) => {
      const src = typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
      const tgt = typeof link.target === "string" ? link.target : (link.target as GraphNode).id;
      return src === selectedNodeId || tgt === selectedNodeId || src === hoveredNodeId || tgt === hoveredNodeId;
    },
    [selectedNodeId, hoveredNodeId]
  );

  const getLinkColor = useCallback(
    (link: GraphLink) => {
      if (isLinkHighlighted(link)) {
        const srcId = typeof link.source === "string" ? link.source : (link.source as GraphNode).id;
        const tgtId = typeof link.target === "string" ? link.target : (link.target as GraphNode).id;
        const activeId = srcId === selectedNodeId || srcId === hoveredNodeId ? srcId : tgtId;
        const nodeMap = new Map(graphData.nodes.map((n) => [n.id, n]));
        const activeNode = nodeMap.get(activeId);
        if (activeNode) {
          const c = new THREE.Color(NODE_TYPE_COLORS[activeNode.type]);
          return `#${c.getHexString()}`;
        }
        return "rgba(255,255,255,0.55)";
      }
      return "rgba(255,255,255,0.18)";
    },
    [isLinkHighlighted, graphData.nodes, selectedNodeId, hoveredNodeId]
  );

  const getLinkWidth = useCallback(
    (link: GraphLink) => {
      const highlighted = isLinkHighlighted(link);
      const strength = link.strength ?? 0.5;
      return highlighted ? (0.6 + strength * 1.2) * 2.0 : 0.6 + strength * 1.2;
    },
    [isLinkHighlighted]
  );

  const nodeMap = useMemo(() => new Map(graphData.nodes.map((n) => [n.id, n])), [graphData.nodes]);

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
        linkDirectionalParticleWidth={1.5}
        linkDirectionalParticleSpeed={0.006}
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
      <div className="cg-face-legend">
        <div className="cg-face-legend-title">Cube Faces</div>
        <div className="cg-face-item">
          <span className="cg-face-swatch" style={{ background: FACE_COLORS.brand }} />
          <span>Brands</span>
        </div>
        <div className="cg-face-item">
          <span className="cg-face-swatch" style={{ background: FACE_COLORS.company }} />
          <span>Companies</span>
        </div>
        <div className="cg-face-item">
          <span className="cg-face-swatch" style={{ background: FACE_COLORS.category }} />
          <span>Categories</span>
        </div>
        <div className="cg-face-item">
          <span className="cg-face-swatch" style={{ background: FACE_COLORS.product }} />
          <span>Products</span>
        </div>
        <div className="cg-face-swatch-note">Click nodes to rotate</div>
      </div>
    </div>
  );
}