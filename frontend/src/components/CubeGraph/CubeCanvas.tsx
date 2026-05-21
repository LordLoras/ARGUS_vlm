import { useRef, useEffect, useCallback, useState, useMemo } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";
import type { GraphData, GraphNode, GraphLink, NodeType } from "./types";
import { NODE_TYPE_COLORS, NODE_TYPE_SIZES, FACE_COLORS } from "./types";

interface Props {
  graphData: GraphData;
  selectedNodeId: string | null;
  onNodeClick: (node: GraphNode) => void;
  hoveredNodeId: string | null;
  onNodeHover: (node: GraphNode | null) => void;
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
      const t = nodeMap.get(tgt);
      if (t && result[t.type as NodeType]) result[t.type as NodeType].push(t.label);
    } else if (tgt === nodeId) {
      const s = nodeMap.get(src);
      if (s && result[s.type as NodeType]) result[s.type as NodeType].push(s.label);
    }
  }
  return result;
}

function easeOutElastic(t: number): number {
  if (t === 0 || t === 1) return t;
  return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1;
}

function createFaceTexture(
  title: string,
  items: string[],
  color: string,
  opts: { isTop?: boolean; nodeLabel?: string; nodeType?: string; totalConnections?: number } = {}
): THREE.CanvasTexture {
  const S = 512;
  const canvas = document.createElement("canvas");
  canvas.width = S;
  canvas.height = S;
  const ctx = canvas.getContext("2d")!;

  // Background gradient
  const grad = ctx.createLinearGradient(0, 0, 0, S);
  grad.addColorStop(0, "#0e1117");
  grad.addColorStop(1, "#0a0c10");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, S, S);

  // Color accent wash at top
  const topWash = ctx.createLinearGradient(0, 0, 0, S * 0.45);
  topWash.addColorStop(0, color);
  topWash.addColorStop(1, "transparent");
  ctx.globalAlpha = 0.15;
  ctx.fillStyle = topWash;
  ctx.fillRect(0, 0, S, S);
  ctx.globalAlpha = 1;

  // Border
  ctx.strokeStyle = color;
  ctx.globalAlpha = 0.35;
  ctx.lineWidth = 2;
  ctx.strokeRect(6, 6, S - 12, S - 12);
  ctx.globalAlpha = 1;

  // Corner dots
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.5;
  [[10, 10], [S - 10, 10], [10, S - 10], [S - 10, S - 10]].forEach(([x, y]) => {
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.globalAlpha = 1;

  if (opts.isTop) {
    // Top face: big label + type badge
    ctx.fillStyle = color;
    ctx.font = `bold 28px Inter, system-ui, -apple-system, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const label = opts.nodeLabel ?? title;
    const maxWidth = S - 60;
    let labelLines: string[] = [];
    if (ctx.measureText(label).width > maxWidth) {
      const words = label.split(" ");
      let line = "";
      for (const w of words) {
        if (ctx.measureText(line + " " + w).width > maxWidth && line) {
          labelLines.push(line.trim());
          line = w;
        } else {
          line += " " + w;
        }
      }
      labelLines.push(line.trim());
    } else {
      labelLines = [label];
    }
    labelLines.forEach((line, i) => {
      ctx.fillText(line, S / 2, S * 0.38 + i * 36, maxWidth);
    });

    // Type badge
    if (opts.nodeType) {
      const typeLabel = opts.nodeType.toUpperCase();
      ctx.font = `600 14px "JetBrains Mono", ui-monospace, monospace`;
      const typeWidth = ctx.measureText(typeLabel).width + 20;
      const badgeX = (S - typeWidth) / 2;
      const badgeY = S * 0.56;
      ctx.fillStyle = `${color}25`;
      ctx.strokeStyle = `${color}50`;
      ctx.lineWidth = 1;
      roundRect(ctx, badgeX, badgeY, typeWidth, 24, 4);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.fillText(typeLabel, badgeX + 10, badgeY + 17);
    }

    // Connection count
    if (opts.totalConnections !== undefined) {
      ctx.fillStyle = "#4a5060";
      ctx.font = `12px "JetBrains Mono", ui-monospace, monospace`;
      ctx.fillText(`${opts.totalConnections} connections`, S / 2, S * 0.72);
    }

    // "Click to explore"
    ctx.fillStyle = "#3a3f4a";
    ctx.font = `11px "JetBrains Mono", ui-monospace, monospace`;
    ctx.fillText("Click to rotate", S / 2, S * 0.84);
  } else {
    // Data face: title + list
    ctx.fillStyle = color;
    ctx.font = `bold 18px "JetBrains Mono", ui-monospace, monospace`;
    ctx.textAlign = "left";
    ctx.fillText(title.toUpperCase(), 24, 38);

    // Count badge
    ctx.font = `600 13px "JetBrains Mono", ui-monospace, monospace`;
    const countStr = `${items.length}`;
    const countWidth = ctx.measureText(countStr).width + 16;
    ctx.fillStyle = `${color}20`;
    roundRect(ctx, S - 24 - countWidth, 22, countWidth, 22, 3);
    ctx.fill();
    ctx.fillStyle = color;
    ctx.textAlign = "center";
    ctx.fillText(countStr, S - 24 - countWidth / 2, 38);
    ctx.textAlign = "left";

    // Divider line
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.2;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(24, 52);
    ctx.lineTo(S - 24, 52);
    ctx.stroke();
    ctx.globalAlpha = 1;

    if (items.length === 0) {
      ctx.fillStyle = "#3a3f4a";
      ctx.font = `15px Inter, system-ui, -apple-system, sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText("No connections", S / 2, S * 0.5);
      ctx.textAlign = "left";
    } else {
      // Items as chips
      const maxItems = 6;
      const display = items.slice(0, maxItems);
      const chipH = 28;
      const chipGap = 6;
      const chipPadH = 10;
      const startY = 64;
      const maxWidth = S - 48;

      ctx.font = `13px Inter, system-ui, -apple-system, sans-serif`;
      display.forEach((item, i) => {
        const y = startY + i * (chipH + chipGap);
        const textW = ctx.measureText(item).width;
        const w = Math.min(textW + chipPadH * 2, maxWidth);

        ctx.fillStyle = `${color}15`;
        ctx.strokeStyle = `${color}30`;
        ctx.lineWidth = 1;
        roundRect(ctx, 24, y, w, chipH, 4);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = "#d4d8e0";
        ctx.fillText(item, 24 + chipPadH, y + 18, maxWidth - chipPadH * 2);
      });

      if (items.length > maxItems) {
        ctx.fillStyle = "#6b7280";
        ctx.font = `12px "JetBrains Mono", ui-monospace, monospace`;
        ctx.fillText(`+${items.length - maxItems} more`, 24, startY + display.length * (chipH + chipGap));
      }
    }
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  return tex;
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function buildCubeMaterials(node: GraphNode, graphData: GraphData): THREE.Material[] {
  const connMap = buildConnectionMap(node.id, graphData);
  const color = NODE_TYPE_COLORS[node.type];
  const totalConnections = Object.values(connMap).flat().length;

  const topTex = createFaceTexture(node.label, [], color, {
    isTop: true,
    nodeLabel: node.label,
    nodeType: NODE_TYPE_LABELS[node.type] ?? node.type,
    totalConnections,
  });

  const infoItems = [
    node.founded ? `Est. ${node.founded}` : "",
    node.headquarters ?? "",
    node.website ?? "",
  ].filter(Boolean);

  const bottomTex = createFaceTexture("info", infoItems, "#6b7280", {});
  const brandTex = createFaceTexture("brands", connMap.brand, FACE_COLORS.brand, {});
  const companyTex = createFaceTexture("companies", connMap.company, FACE_COLORS.company, {});
  const categoryTex = createFaceTexture("categories", connMap.category, FACE_COLORS.category, {});
  const productTex = createFaceTexture("products", connMap.product, FACE_COLORS.product, {});

  // BoxGeometry order: +X, -X, +Y, -Y, +Z, -Z
  return [
    new THREE.MeshStandardMaterial({ map: brandTex, roughness: 0.35, metalness: 0.55 }),
    new THREE.MeshStandardMaterial({ map: productTex, roughness: 0.35, metalness: 0.55 }),
    new THREE.MeshStandardMaterial({ map: topTex, roughness: 0.25, metalness: 0.65 }),
    new THREE.MeshStandardMaterial({ map: bottomTex, roughness: 0.4, metalness: 0.45 }),
    new THREE.MeshStandardMaterial({ map: companyTex, roughness: 0.35, metalness: 0.55 }),
    new THREE.MeshStandardMaterial({ map: categoryTex, roughness: 0.35, metalness: 0.55 }),
  ];
}

const NODE_TYPE_LABELS: Record<string, string> = {
  brand: "Brand",
  company: "Company",
  category: "Category",
  product: "Product",
  subsidiary: "Subsidiary",
};

const FACE_ROTATIONS: Record<string, { x: number; y: number }> = {
  brand: { x: 0, y: Math.PI / 2 },
  product: { x: 0, y: -Math.PI / 2 },
  company: { x: 0, y: 0 },
  category: { x: 0, y: Math.PI },
  _default: { x: -Math.PI / 6, y: Math.PI / 5 },
};

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
    fg.d3Force("charge")?.strength(-300);
    fg.d3Force("link")?.distance((link: any) => {
      const strength = link.strength ?? 0.5;
      return 85 + (1 - strength) * 55;
    });
  }, [graphData]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      const fg = fgRef.current;
      if (!fg) return;
      const distance = 140;
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
      const cubeSize = size * (isSelected ? 1.9 : isHovered ? 1.5 : 1.15);

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

      // Edge wireframe for all nodes (subtle) and strong for selected
      const edgesGeo = new THREE.EdgesGeometry(geometry);
      const edgesMat = new THREE.LineBasicMaterial({
        color: NODE_TYPE_COLORS[node.type],
        transparent: true,
        opacity: isSelected ? 0.9 : isHovered ? 0.5 : 0.15,
      });
      group.add(new THREE.LineSegments(edgesGeo, edgesMat));

      if (isSelected || isHovered) {
        const glowSize = cubeSize * (isSelected ? 1.35 : 1.2);
        const glowGeo = new THREE.BoxGeometry(glowSize, glowSize, glowSize);
        const glowMat = new THREE.MeshBasicMaterial({
          color: NODE_TYPE_COLORS[node.type],
          transparent: true,
          opacity: isSelected ? 0.1 : 0.04,
          side: THREE.BackSide,
        });
        group.add(new THREE.Mesh(glowGeo, glowMat));
      }

      // Idle gentle rotation for unselected nodes
      if (!isSelected) {
        group.rotation.x = Math.PI / 8;
        group.rotation.y = Math.PI / 6;
      }

      cubeGroupRefs.current.set(node.id, group);
      return group;
    },
    [selectedNodeId, hoveredNodeId, graphData, dataKey]
  );

  // Animate selected cube rotation
  useEffect(() => {
    if (!selectedNodeId) return;

    const group = cubeGroupRefs.current.get(selectedNodeId);
    if (!group) return;

    // Determine which face to show based on node type
    const node = graphData.nodes.find((n) => n.id === selectedNodeId);
    const targetType = node?.type ?? "company";
    const rotTarget = FACE_ROTATIONS[targetType] ?? FACE_ROTATIONS._default;

    const startRot = { x: group.rotation.x, y: group.rotation.y };
    const startScale = group.scale.x;
    const startTime = performance.now();
    const duration = 900;

    // Reset all other cubes
    cubeGroupRefs.current.forEach((g, id) => {
      if (id !== selectedNodeId) {
        g.rotation.x = Math.PI / 8;
        g.rotation.y = Math.PI / 6;
      }
    });

    const animate = () => {
      const elapsed = performance.now() - startTime;
      const t = Math.min(elapsed / duration, 1);
      const eased = easeOutElastic(t);

      group.rotation.x = startRot.x + (rotTarget.x - startRot.x) * eased;
      group.rotation.y = startRot.y + (rotTarget.y - startRot.y) * eased;

      if (t < 1) {
        animFrame.current = requestAnimationFrame(animate);
      }
    };
    cancelAnimationFrame(animFrame.current);
    animFrame.current = requestAnimationFrame(animate);

    return () => cancelAnimationFrame(animFrame.current);
  }, [selectedNodeId, graphData.nodes]);

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
      const base = 0.6 + strength * 1.2;
      return highlighted ? base * 2.0 : base;
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
        linkDirectionalParticles={2}
        linkDirectionalParticleWidth={1.8}
        linkDirectionalParticleSpeed={0.008}
        linkDirectionalArrowLength={0}
        linkCurvature={0}
        linkVisibility={true}
        backgroundColor="#08090b"
        warmupTicks={100}
        cooldownTicks={600}
        d3AlphaDecay={0.012}
        d3VelocityDecay={0.35}
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
        <div className="cg-face-swatch-note">Click to rotate</div>
      </div>
      <div className="kg-controls-hint">
        <span>Drag to orbit</span>
        <span className="kg-hint-sep" />
        <span>Scroll to zoom</span>
        <span className="kg-hint-sep" />
        <span>Click to explore</span>
      </div>
    </div>
  );
}