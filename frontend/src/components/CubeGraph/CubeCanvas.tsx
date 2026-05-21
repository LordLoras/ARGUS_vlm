import { useRef, useEffect, useCallback, useState, useMemo } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";
import type { GraphData, GraphNode, GraphLink, NodeType } from "./types";
import { NODE_TYPE_COLORS, NODE_TYPE_SIZES, FACE_COLORS } from "./types";

interface Props {
  graphData: GraphData;
  selectedNodeId: string | null;
  onNodeClick: (node: GraphNode) => void;
  onBackgroundClick?: () => void;
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

const TEX_RES = 256;

const texCache = new Map<string, THREE.CanvasTexture>();
const matCache = new Map<string, THREE.Material[]>();
const geometryCache = new Map<string, THREE.BoxGeometry>();
const edgesCache = new Map<string, THREE.EdgesGeometry>();
const lineMatCache = new Map<string, THREE.LineBasicMaterial>();
const glowMatCache = new Map<string, THREE.MeshBasicMaterial>();

const NODE_TYPE_LABELS: Record<string, string> = {
  brand: "Brand",
  company: "Company",
  category: "Category",
  product: "Product",
  subsidiary: "Subsidiary",
};

const FACE_ROTATIONS: Record<string, { x: number; y: number }> = {
  brand: { x: 0, y: -Math.PI / 2 },
  product: { x: 0, y: Math.PI / 2 },
  company: { x: 0, y: 0 },
  category: { x: 0, y: Math.PI },
  _default: { x: -Math.PI / 6, y: Math.PI / 5 },
};

const FACE_PRIORITIES: Record<NodeType, Array<keyof ConnectionMap>> = {
  company: ["brand", "product", "category", "company"],
  brand: ["product", "category", "company", "brand"],
  category: ["product", "brand", "company", "category"],
  product: ["category", "brand", "company", "product"],
  subsidiary: ["company", "brand", "product", "category"],
};

function easeOutElastic(t: number): number {
  if (t === 0 || t === 1) return t;
  return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * ((2 * Math.PI) / 3)) + 1;
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

function getEndpointId(endpoint: string | GraphNode): string {
  return typeof endpoint === "string" ? endpoint : endpoint.id;
}

function graphLinkKey(link: GraphLink): string {
  return `${getEndpointId(link.source)}:${link.label ?? ""}:${getEndpointId(link.target)}`;
}

function truncateText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    if (ctx.measureText(`${text.slice(0, mid)}...`).width <= maxWidth) lo = mid;
    else hi = mid - 1;
  }
  return `${text.slice(0, Math.max(0, lo)).trimEnd()}...`;
}

function wrapText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number): string[] {
  const words = text.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let line = "";

  for (const word of words.length ? words : [text]) {
    const candidate = line ? `${line} ${word}` : word;
    if (ctx.measureText(candidate).width <= maxWidth) {
      line = candidate;
      continue;
    }
    if (line) lines.push(line);
    line = ctx.measureText(word).width <= maxWidth ? word : truncateText(ctx, word, maxWidth);
    if (lines.length === maxLines - 1) break;
  }

  if (line && lines.length < maxLines) lines.push(line);
  if (lines.length === maxLines && words.join(" ") !== lines.join(" ")) {
    lines[maxLines - 1] = truncateText(ctx, lines[maxLines - 1], maxWidth);
  }
  return lines.length ? lines : [truncateText(ctx, text, maxWidth)];
}

function applyTextureQuality(tex: THREE.CanvasTexture): THREE.CanvasTexture {
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  tex.generateMipmaps = true;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.magFilter = THREE.LinearFilter;
  tex.needsUpdate = true;
  return tex;
}

function createFaceTexture(
  title: string,
  items: string[],
  color: string,
  opts: { isTop?: boolean; nodeLabel?: string; nodeType?: string; totalConnections?: number } = {}
): THREE.CanvasTexture {
  const cacheKey = `${title}|${items.join(",")}|${color}|${opts.isTop ? 1 : 0}|${opts.nodeLabel ?? ""}|${opts.nodeType ?? ""}|${opts.totalConnections ?? ""}`;
  if (texCache.has(cacheKey)) {
    return texCache.get(cacheKey)!;
  }

  const S = TEX_RES;
  const canvas = document.createElement("canvas");
  canvas.width = S;
  canvas.height = S;
  const ctx = canvas.getContext("2d")!;

  const grad = ctx.createLinearGradient(0, 0, 0, S);
  grad.addColorStop(0, "#131821");
  grad.addColorStop(1, "#090d13");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, S, S);

  ctx.fillStyle = color;
  ctx.globalAlpha = 0.18;
  const topWash = ctx.createLinearGradient(0, 0, 0, S * 0.45);
  topWash.addColorStop(0, color);
  topWash.addColorStop(1, "transparent");
  ctx.fillStyle = topWash;
  ctx.fillRect(0, 0, S, S);
  ctx.globalAlpha = 1;

  ctx.strokeStyle = color;
  ctx.globalAlpha = 0.45;
  ctx.lineWidth = 2;
  ctx.strokeRect(4, 4, S - 8, S - 8);
  ctx.globalAlpha = 1;

  ctx.fillStyle = color;
  ctx.globalAlpha = 0.6;
  [[8, 8], [S - 8, 8], [8, S - 8], [S - 8, S - 8]].forEach(([x, y]) => {
    ctx.beginPath();
    ctx.arc(x, y, 2, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.globalAlpha = 1;

  if (opts.isTop) {
    ctx.fillStyle = color;
    ctx.font = `bold 22px Inter, system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const maxWidth = S - 40;
    const label = opts.nodeLabel ?? title;
    const labelLines = wrapText(ctx, label, maxWidth, 3);
    const labelStartY = S * 0.35 - (labelLines.length - 1) * 13;
    labelLines.forEach((line, i) => {
      ctx.fillText(line, S / 2, labelStartY + i * 26, maxWidth);
    });

    if (opts.nodeType) {
      const typeLabel = opts.nodeType.toUpperCase();
      ctx.font = `600 11px "JetBrains Mono", ui-monospace, monospace`;
      const typeWidth = ctx.measureText(typeLabel).width + 16;
      const badgeX = (S - typeWidth) / 2;
      const badgeY = S * 0.56;
      ctx.fillStyle = `${color}25`;
      ctx.strokeStyle = `${color}50`;
      ctx.lineWidth = 1;
      roundRect(ctx, badgeX, badgeY, typeWidth, 20, 3);
      ctx.fill();
      ctx.stroke();
      ctx.textAlign = "left";
      ctx.fillStyle = color;
      ctx.fillText(typeLabel, badgeX + 8, badgeY + 14);
      ctx.textAlign = "center";
    }

    if (opts.totalConnections !== undefined) {
      ctx.fillStyle = "#4a5060";
      ctx.font = `11px "JetBrains Mono", ui-monospace, monospace`;
      ctx.fillText(`${opts.totalConnections} conn`, S / 2, S * 0.72);
    }

    ctx.fillStyle = "#3a3f4a";
    ctx.font = `10px "JetBrains Mono", ui-monospace, monospace`;
    ctx.fillText("Click to rotate", S / 2, S * 0.84);
  } else {
    ctx.fillStyle = color;
    ctx.font = `bold 14px "JetBrains Mono", ui-monospace, monospace`;
    ctx.textAlign = "left";
    ctx.fillText(title.toUpperCase(), 16, 28);

    ctx.font = `600 11px "JetBrains Mono", ui-monospace, monospace`;
    const countStr = `${items.length}`;
    const countWidth = ctx.measureText(countStr).width + 12;
    ctx.fillStyle = `${color}20`;
    roundRect(ctx, S - 16 - countWidth, 16, countWidth, 18, 3);
    ctx.fill();
    ctx.fillStyle = color;
    ctx.textAlign = "center";
    ctx.fillText(countStr, S - 16 - countWidth / 2, 30);
    ctx.textAlign = "left";

    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.15;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(16, 42);
    ctx.lineTo(S - 16, 42);
    ctx.stroke();
    ctx.globalAlpha = 1;

    if (items.length === 0) {
      ctx.fillStyle = "#3a3f4a";
      ctx.font = `12px Inter, system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText("Empty", S / 2, S * 0.5);
      ctx.textAlign = "left";
    } else {
      const maxItems = 5;
      const display = items.slice(0, maxItems);
      const chipH = 22;
      const chipGap = 4;
      const chipPadH = 8;
      const startY = 50;
      const maxWidth = S - 32;

      ctx.font = `11px Inter, system-ui, sans-serif`;
      display.forEach((item, i) => {
        const y = startY + i * (chipH + chipGap);
        const textW = ctx.measureText(item).width;
        const w = Math.min(textW + chipPadH * 2, maxWidth);

        ctx.fillStyle = `${color}12`;
        ctx.strokeStyle = `${color}25`;
        ctx.lineWidth = 1;
        roundRect(ctx, 16, y, w, chipH, 3);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = "#c8ccd4";
        ctx.fillText(truncateText(ctx, item, maxWidth - chipPadH * 2), 16 + chipPadH, y + 14);
      });

      if (items.length > maxItems) {
        ctx.fillStyle = "#6b7280";
        ctx.font = `10px "JetBrains Mono", ui-monospace, monospace`;
        ctx.fillText(`+${items.length - maxItems}`, 16, startY + display.length * (chipH + chipGap));
      }
    }
  }

  const tex = applyTextureQuality(new THREE.CanvasTexture(canvas));
  texCache.set(cacheKey, tex);
  return tex;
}

function buildCubeMaterials(node: GraphNode, graphData: GraphData): THREE.Material[] {
  const connMap = buildConnectionMap(node.id, graphData);
  const color = NODE_TYPE_COLORS[node.type];
  const totalConnections = Object.values(connMap).flat().length;
  const connectionSignature = Object.entries(connMap)
    .map(([type, labels]) => `${type}:${labels.join("|")}`)
    .join(";");

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

  const cacheKey = `mat:${node.id}:${node.label}:${connectionSignature}:${infoItems.join("|")}`;
  if (matCache.has(cacheKey)) return matCache.get(cacheKey)!;

  const mats = [
    new THREE.MeshBasicMaterial({ map: brandTex, toneMapped: false }),
    new THREE.MeshBasicMaterial({ map: productTex, toneMapped: false }),
    new THREE.MeshBasicMaterial({ map: topTex, toneMapped: false }),
    new THREE.MeshBasicMaterial({ map: bottomTex, toneMapped: false }),
    new THREE.MeshBasicMaterial({ map: companyTex, toneMapped: false }),
    new THREE.MeshBasicMaterial({ map: categoryTex, toneMapped: false }),
  ];
  matCache.set(cacheKey, mats);
  return mats;
}

function buildConnectionMap(nodeId: string, graphData: GraphData): ConnectionMap {
  const nodeMap = new Map(graphData.nodes.map((n) => [n.id, n]));
  const result: ConnectionMap = { brand: [], company: [], category: [], product: [], subsidiary: [] };
  const addLabel = (node: GraphNode) => {
    const bucket = result[node.type as NodeType];
    if (bucket && !bucket.includes(node.label)) bucket.push(node.label);
  };
  for (const link of graphData.links) {
    const src = getEndpointId(link.source);
    const tgt = getEndpointId(link.target);
    if (src === nodeId) {
      const t = nodeMap.get(tgt);
      if (t) addLabel(t);
    } else if (tgt === nodeId) {
      const s = nodeMap.get(src);
      if (s) addLabel(s);
    }
  }
  return result;
}

function getFocusedFaceRotation(node: GraphNode, graphData: GraphData): { x: number; y: number } {
  const connMap = buildConnectionMap(node.id, graphData);
  const priority = FACE_PRIORITIES[node.type] ?? ["brand", "product", "company", "category"];
  const face = priority.find((type) => connMap[type].length > 0) ?? priority[0];
  return FACE_ROTATIONS[face] ?? FACE_ROTATIONS._default;
}

function getBoxGeometry(size: number): THREE.BoxGeometry {
  const key = `geo:${size.toFixed(2)}`;
  if (geometryCache.has(key)) return geometryCache.get(key)!;
  const geo = new THREE.BoxGeometry(size, size, size);
  geometryCache.set(key, geo);
  return geo;
}

function getEdgesGeometry(size: number): THREE.EdgesGeometry {
  const key = `edg:${size.toFixed(2)}`;
  if (edgesCache.has(key)) return edgesCache.get(key)!;
  const geo = new THREE.EdgesGeometry(getBoxGeometry(size));
  edgesCache.set(key, geo);
  return geo;
}

function getLineMaterial(type: NodeType, opacity: number): THREE.LineBasicMaterial {
  const key = `line:${type}:${opacity.toFixed(2)}`;
  if (lineMatCache.has(key)) return lineMatCache.get(key)!;
  const mat = new THREE.LineBasicMaterial({
    color: NODE_TYPE_COLORS[type],
    transparent: true,
    opacity,
  });
  lineMatCache.set(key, mat);
  return mat;
}

function getGlowMaterial(type: NodeType, opacity: number): THREE.MeshBasicMaterial {
  const key = `glow:${type}:${opacity.toFixed(2)}`;
  if (glowMatCache.has(key)) return glowMatCache.get(key)!;
  const mat = new THREE.MeshBasicMaterial({
    color: NODE_TYPE_COLORS[type],
    transparent: true,
    opacity,
    side: THREE.BackSide,
  });
  glowMatCache.set(key, mat);
  return mat;
}

function disposeCaches() {
  texCache.forEach((tex) => tex.dispose());
  matCache.forEach((materials) => materials.forEach((mat) => mat.dispose()));
  geometryCache.forEach((geo) => geo.dispose());
  edgesCache.forEach((geo) => geo.dispose());
  lineMatCache.forEach((mat) => mat.dispose());
  glowMatCache.forEach((mat) => mat.dispose());
  texCache.clear();
  matCache.clear();
  geometryCache.clear();
  edgesCache.clear();
  lineMatCache.clear();
  glowMatCache.clear();
}

export function CubeCanvas({
  graphData,
  selectedNodeId,
  onNodeClick,
  onBackgroundClick,
  hoveredNodeId,
  onNodeHover,
}: Props) {
  const fgRef = useRef<any>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const cubeGroupRefs = useRef(new Map<string, THREE.Group>());
  const animFrame = useRef<number>(0);
  const hadSelectionRef = useRef(false);
  const selectionPinRef = useRef<string | null>(null);

  const nodeMap = useMemo(() => new Map(graphData.nodes.map((n) => [n.id, n])), [graphData.nodes]);
  const graphSignature = useMemo(
    () => `${graphData.nodes.map((n) => n.id).join(",")}::${graphData.links.map(graphLinkKey).join(",")}`,
    [graphData.nodes, graphData.links]
  );

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
    return () => {
      cancelAnimationFrame(animFrame.current);
      cubeGroupRefs.current.clear();
      disposeCaches();
    };
  }, []);

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-280);
    fg.d3Force("link")?.distance((link: any) => {
      const strength = link.strength ?? 0.5;
      return 90 + (1 - strength) * 50;
    });
  }, [graphData]);

  const flyToNode = useCallback((nodeId: string) => {
    const fg = fgRef.current;
    if (!fg) return;
    const findNode = (): GraphNode | undefined => {
      const liveGraph = typeof fg.graphData === "function" ? fg.graphData() : null;
      const liveNode = liveGraph?.nodes?.find((n: GraphNode) => n.id === nodeId);
      return liveNode ?? graphData.nodes.find((n) => n.id === nodeId);
    };
    const clearSelectionPin = () => {
      if (!selectionPinRef.current) return;
      const liveGraph = typeof fg.graphData === "function" ? fg.graphData() : null;
      const pinnedNode = liveGraph?.nodes?.find((n: GraphNode) => n.id === selectionPinRef.current);
      if (pinnedNode && (pinnedNode as any).__argusSelectionPin) {
        delete pinnedNode.fx;
        delete pinnedNode.fy;
        delete pinnedNode.fz;
        delete (pinnedNode as any).__argusSelectionPin;
      }
      selectionPinRef.current = null;
    };

    let cancelled = false;
    let attempts = 0;
    let timer: number | undefined;
    const tryMove = () => {
      if (cancelled) return;
      const node = findNode();
      if (node && node.x != null && node.y != null && node.z != null) {
        clearSelectionPin();
        node.fx = node.x;
        node.fy = node.y;
        node.fz = node.z;
        (node as any).__argusSelectionPin = true;
        selectionPinRef.current = node.id;
        const baseSize = NODE_TYPE_SIZES[node.type] ?? 5;
        const distance = Math.max(92, baseSize * 12);
        const offset = new THREE.Vector3(0.46, 0.32, 1).normalize().multiplyScalar(distance);
        const target = { x: node.x, y: node.y, z: node.z };
        fg.cameraPosition(
          { x: node.x + offset.x, y: node.y + offset.y, z: node.z + offset.z },
          target,
          1200
        );
        return;
      }
      if (attempts < 10) {
        attempts += 1;
        timer = window.setTimeout(tryMove, 160);
      }
    };
    tryMove();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [graphData.nodes]);

  useEffect(() => {
    if (!selectedNodeId) {
      if (hadSelectionRef.current && fgRef.current) {
        const liveGraph = typeof fgRef.current.graphData === "function" ? fgRef.current.graphData() : null;
        const pinnedNode = liveGraph?.nodes?.find((n: GraphNode) => n.id === selectionPinRef.current);
        if (pinnedNode && (pinnedNode as any).__argusSelectionPin) {
          delete pinnedNode.fx;
          delete pinnedNode.fy;
          delete pinnedNode.fz;
          delete (pinnedNode as any).__argusSelectionPin;
        }
        selectionPinRef.current = null;
        fgRef.current.zoomToFit(950, 80);
        cubeGroupRefs.current.forEach((g) => {
          g.rotation.x = Math.PI / 8;
          g.rotation.y = Math.PI / 6;
        });
      }
      return;
    }
    hadSelectionRef.current = true;
    const cleanup = flyToNode(selectedNodeId);
    return cleanup ?? undefined;
  }, [selectedNodeId, flyToNode]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      onNodeClick(node);
    },
    [onNodeClick]
  );

  const customNodeRenderer = useCallback(
    (node: GraphNode) => {
      const isSelected = node.id === selectedNodeId;
      const isHovered = node.id === hoveredNodeId;
      const size = NODE_TYPE_SIZES[node.type] ?? 5;
      const cubeSize = size * (isSelected ? 3.1 : isHovered ? 1.45 : 1.1);

      const group = new THREE.Group();
      const geometry = getBoxGeometry(cubeSize);

      const materials = buildCubeMaterials(node, graphData);
      const mesh = new THREE.Mesh(geometry, materials);
      group.add(mesh);

      const edgesGeo = getEdgesGeometry(cubeSize);
      group.add(new THREE.LineSegments(edgesGeo, getLineMaterial(node.type, isSelected ? 0.95 : isHovered ? 0.56 : 0.24)));

      if (isSelected || isHovered) {
        const glowSize = cubeSize * (isSelected ? 1.3 : 1.15);
        const glowGeo = getBoxGeometry(glowSize);
        group.add(new THREE.Mesh(glowGeo, getGlowMaterial(node.type, isSelected ? 0.12 : 0.05)));
      }

      if (isSelected) {
        const focusedRotation = getFocusedFaceRotation(node, graphData);
        group.rotation.x = focusedRotation.x;
        group.rotation.y = focusedRotation.y;
      } else {
        group.rotation.x = Math.PI / 8;
        group.rotation.y = Math.PI / 6;
      }

      cubeGroupRefs.current.set(node.id, group);
      return group;
    },
    [selectedNodeId, hoveredNodeId, graphData, graphSignature]
  );

  useEffect(() => {
    if (!selectedNodeId) return;
    const group = cubeGroupRefs.current.get(selectedNodeId);
    if (!group) return;

    const node = graphData.nodes.find((n) => n.id === selectedNodeId);
    const rotTarget = node ? getFocusedFaceRotation(node, graphData) : FACE_ROTATIONS._default;

    const startRot = { x: group.rotation.x, y: group.rotation.y };
    const startTime = performance.now();
    const duration = 800;

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
      if (t < 1) animFrame.current = requestAnimationFrame(animate);
    };
    cancelAnimationFrame(animFrame.current);
    animFrame.current = requestAnimationFrame(animate);

    return () => cancelAnimationFrame(animFrame.current);
  }, [selectedNodeId, graphData.nodes]);

  const isLinkHighlighted = useCallback(
    (link: GraphLink) => {
      const src = getEndpointId(link.source);
      const tgt = getEndpointId(link.target);
      return src === selectedNodeId || tgt === selectedNodeId || src === hoveredNodeId || tgt === hoveredNodeId;
    },
    [selectedNodeId, hoveredNodeId]
  );

  const getLinkColor = useCallback(
    (link: GraphLink) => {
      if (isLinkHighlighted(link)) {
        const srcId = getEndpointId(link.source);
        const tgtId = getEndpointId(link.target);
        const activeId = srcId === selectedNodeId || srcId === hoveredNodeId ? srcId : tgtId;
        const activeNode = nodeMap.get(activeId);
        if (activeNode) {
          const c = new THREE.Color(NODE_TYPE_COLORS[activeNode.type]);
          return `#${c.getHexString()}`;
        }
        return "rgba(255,255,255,0.5)";
      }
      return "rgba(255,255,255,0.12)";
    },
    [isLinkHighlighted, nodeMap, selectedNodeId, hoveredNodeId]
  );

  const getLinkWidth = useCallback(
    (link: GraphLink) => {
      const highlighted = isLinkHighlighted(link);
      const strength = link.strength ?? 0.5;
      const base = 0.34 + strength * 0.64;
      return highlighted ? base * 2.4 : base;
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
        nodeColor={() => "#ffffff"}
        nodeThreeObject={customNodeRenderer}
        nodeThreeObjectExtend={false}
        onNodeClick={handleNodeClick}
        onBackgroundClick={onBackgroundClick}
        onNodeHover={(node: any) => onNodeHover(node ?? null)}
        onNodeDragEnd={(node: any) => { node.fx = node.x; node.fy = node.y; node.fz = node.z; }}
        linkColor={getLinkColor as any}
        linkWidth={getLinkWidth}
        linkDirectionalParticles={(link: any) => (isLinkHighlighted(link) ? 2 : 0)}
        linkDirectionalParticleWidth={1.4}
        linkDirectionalParticleSpeed={0.007}
        linkDirectionalArrowLength={0}
        linkCurvature={0}
        linkVisibility={true}
        backgroundColor="#08090b"
        warmupTicks={60}
        cooldownTicks={400}
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.4}
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
