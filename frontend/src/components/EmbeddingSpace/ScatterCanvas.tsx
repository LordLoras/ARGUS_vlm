import { useRef, useEffect, useCallback, useState } from "react";
import * as THREE from "three";
import SpriteText from "three-spritetext";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

export interface ScatterPoint {
  id: string;
  x: number;
  y: number;
  z: number;
  category: string;
  confidence: number;
  brand: string;
  label: string;
}

interface Props {
  points: ScatterPoint[];
  selectedId: string | null;
  onPointClick: (point: ScatterPoint) => void;
  onBackgroundClick?: () => void;
  hoveredId: string | null;
  onPointHover: (point: ScatterPoint | null, position?: { x: number; y: number }) => void;
  categoryColors: Record<string, string>;
  activeCategories: Set<string>;
  compact?: boolean;
}

const POINT_SIZE_BASE = 0.74;
const POINT_SIZE_MAX = 1.62;
const BG_COLOR = 0x06070a;
const RAYCASTER_THRESHOLD = 2.0;

const sphereGeo = new THREE.SphereGeometry(1, 28, 20);
const shellGeo = new THREE.SphereGeometry(1.08, 28, 18);
const haloGeo = new THREE.TorusGeometry(1.32, 0.025, 8, 72);

const colorCache = new Map<string, THREE.Color>();
function getColor(hex: string): THREE.Color {
  let c = colorCache.get(hex);
  if (!c) {
    c = new THREE.Color(hex);
    colorCache.set(hex, c);
  }
  return c;
}

const glowTextureCache = new Map<string, THREE.CanvasTexture>();
function getGlowTexture(hex: string): THREE.CanvasTexture {
  let texture = glowTextureCache.get(hex);
  if (texture) return texture;

  const color = getColor(hex);
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    texture = new THREE.CanvasTexture(canvas);
    glowTextureCache.set(hex, texture);
    return texture;
  }

  const r = Math.round(color.r * 255);
  const g = Math.round(color.g * 255);
  const b = Math.round(color.b * 255);
  const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, `rgba(255,255,255,0.78)`);
  gradient.addColorStop(0.18, `rgba(${r},${g},${b},0.5)`);
  gradient.addColorStop(0.48, `rgba(${r},${g},${b},0.18)`);
  gradient.addColorStop(1, `rgba(${r},${g},${b},0)`);
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 128, 128);

  texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  glowTextureCache.set(hex, texture);
  return texture;
}

function disposeMaterial(material: THREE.Material | THREE.Material[] | undefined) {
  if (!material) return;
  const materials = Array.isArray(material) ? material : [material];
  materials.forEach((mat) => {
    const mapped = mat as THREE.Material & { map?: THREE.Texture };
    if (mapped.map && !Array.from(glowTextureCache.values()).includes(mapped.map as THREE.CanvasTexture)) {
      mapped.map.dispose();
    }
    mat.dispose();
  });
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child) => {
    disposeMaterial((child as THREE.Mesh | THREE.Sprite).material);
  });
}

function formatCategoryLabel(category: string) {
  return category.replace(/_/g, " ");
}

export function ScatterCanvas({
  points,
  selectedId,
  onPointClick,
  onBackgroundClick,
  hoveredId,
  onPointHover,
  categoryColors,
  activeCategories,
  compact = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const groupRef = useRef<THREE.Group | null>(null);
  const composerRef = useRef<EffectComposer | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const raycaster = useRef(new THREE.Raycaster());
  const mouse = useRef(new THREE.Vector2());
  const meshToId = useRef(new Map<number, string>());
  const idToBubble = useRef(new Map<string, THREE.Group>());
  const animFrame = useRef(0);
  const hoverThrottle = useRef(0);
  const clockRef = useRef(new THREE.Clock());
  const cameraTweenRef = useRef(0);
  const connectionLinesRef = useRef<THREE.LineSegments | null>(null);
  const dustRef = useRef<THREE.Points | null>(null);
  const labelGroupRef = useRef<THREE.Group | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(BG_COLOR);
    scene.fog = new THREE.FogExp2(BG_COLOR, 0.0025);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(50, el.clientWidth / el.clientHeight, 0.1, 800);
    camera.position.set(compact ? 92 : 70, compact ? 58 : 50, compact ? 92 : 70);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    el.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(
      new THREE.Vector2(el.clientWidth, el.clientHeight),
      0.48,
      0.68,
      0.78
    );
    composer.addPass(bloom);
    composerRef.current = composer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.minDistance = 15;
    controls.maxDistance = compact ? 240 : 200;
    controls.target.set(0, 0, 0);
    controls.maxPolarAngle = Math.PI * 0.85;
    controlsRef.current = controls;

    // Ambient + directional
    scene.add(new THREE.AmbientLight(0xffffff, 0.48));
    const dirLight = new THREE.DirectionalLight(0xe8f0ff, 0.55);
    dirLight.position.set(30, 60, 40);
    scene.add(dirLight);
    const rimLight = new THREE.DirectionalLight(0x60a5fa, 0.32);
    rimLight.position.set(-60, 42, -36);
    scene.add(rimLight);

    // Ground plane with subtle gradient
    const groundGeo = new THREE.PlaneGeometry(300, 300);
    const groundMat = new THREE.MeshBasicMaterial({
      color: 0x0a0b0f,
      transparent: true,
      opacity: 0.6,
    });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -44;
    scene.add(ground);

    // Subtle ground reference. The projection itself does not expose literal X/Y/Z axes.
    const gridHelper = new THREE.GridHelper(150, 30, 0x0b1018, 0x080c12);
    gridHelper.position.y = -43.8;
    const gridMaterial = gridHelper.material as THREE.Material | THREE.Material[];
    const gridMaterials = Array.isArray(gridMaterial) ? gridMaterial : [gridMaterial];
    gridMaterials.forEach((mat) => {
      mat.transparent = true;
      mat.opacity = 0.18;
    });
    scene.add(gridHelper);

    // Dust particles for atmosphere
    const dustCount = 600;
    const dustPositions = new Float32Array(dustCount * 3);
    const dustSizes = new Float32Array(dustCount);
    for (let i = 0; i < dustCount; i++) {
      dustPositions[i * 3] = (Math.random() - 0.5) * 200;
      dustPositions[i * 3 + 1] = (Math.random() - 0.5) * 200;
      dustPositions[i * 3 + 2] = (Math.random() - 0.5) * 200;
      dustSizes[i] = Math.random() * 1.5 + 0.5;
    }
    const dustGeo = new THREE.BufferGeometry();
    dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPositions, 3));
    dustGeo.setAttribute("size", new THREE.BufferAttribute(dustSizes, 1));
    const dustMat = new THREE.PointsMaterial({
      color: 0x4a5568,
      size: 0.3,
      transparent: true,
      opacity: 0.15,
      sizeAttenuation: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const dust = new THREE.Points(dustGeo, dustMat);
    scene.add(dust);
    dustRef.current = dust;

    // Connection lines (initially empty)
    const lineGeo = new THREE.BufferGeometry();
    const lineMat = new THREE.LineBasicMaterial({
      color: 0x7c3aed,
      transparent: true,
      opacity: 0.08,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const lineSegments = new THREE.LineSegments(lineGeo, lineMat);
    scene.add(lineSegments);
    connectionLinesRef.current = lineSegments;

    // Point group
    const group = new THREE.Group();
    scene.add(group);
    groupRef.current = group;

    const labelGroup = new THREE.Group();
    scene.add(labelGroup);
    labelGroupRef.current = labelGroup;

    const clock = clockRef.current;

    const animate = () => {
      animFrame.current = requestAnimationFrame(animate);
      const t = clock.getElapsedTime();

      controls.update();

      // Breathing animation on premium data bubbles.
      group.children.forEach((child, i) => {
        if (child.userData.pointId) {
          const base = child.userData.baseScale || 1;
          const breath = 1 + Math.sin(t * 0.78 + i * 0.24) * 0.03;
          child.scale.setScalar(base * breath);
          child.rotation.y = Math.sin(t * 0.2 + i) * 0.08;
          const halo = child.userData.halo as THREE.Mesh | undefined;
          if (halo) halo.rotation.z = t * 0.35 + i * 0.2;
        }
      });

      // Slow dust rotation
      if (dustRef.current) {
        dustRef.current.rotation.y = t * 0.008;
      }

      composer.render();
    };
    animFrame.current = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animFrame.current);
      cancelAnimationFrame(cameraTweenRef.current);
      controls.dispose();
      composer.dispose();
      renderer.dispose();
      if (el.contains(renderer.domElement)) {
        el.removeChild(renderer.domElement);
      }
    };
  }, [compact]);

  // Resize observer
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setDimensions({ width, height });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Apply resize
  useEffect(() => {
    const camera = cameraRef.current;
    const renderer = rendererRef.current;
    const composer = composerRef.current;
    if (!camera || !renderer || !composer) return;
    camera.aspect = dimensions.width / dimensions.height;
    camera.updateProjectionMatrix();
    renderer.setSize(dimensions.width, dimensions.height);
    composer.setSize(dimensions.width, dimensions.height);
  }, [dimensions]);

  // Build point meshes
  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;

    while (group.children.length > 0) {
      const child = group.children[0];
      group.remove(child);
      disposeObject(child);
    }
    meshToId.current.clear();
    idToBubble.current.clear();

    for (const point of points) {
      if (!activeCategories.has(point.category)) continue;

      const color = categoryColors[point.category] || "#7c3aed";
      const size = POINT_SIZE_BASE + Math.min(point.confidence, 1) * (POINT_SIZE_MAX - POINT_SIZE_BASE);
      const threeColor = getColor(color);

      const bubble = new THREE.Group();
      bubble.position.set(point.x, point.y, point.z);
      bubble.scale.setScalar(size);

      const coreMat = new THREE.MeshPhysicalMaterial({
        color: threeColor.clone().lerp(new THREE.Color(0xffffff), 0.12),
        emissive: threeColor,
        emissiveIntensity: 0.28,
        roughness: 0.24,
        metalness: 0.08,
        clearcoat: 0.9,
        clearcoatRoughness: 0.18,
        transparent: true,
        opacity: 0.92,
      });
      const core = new THREE.Mesh(sphereGeo, coreMat);
      bubble.add(core);

      const shellMat = new THREE.MeshBasicMaterial({
        color: threeColor,
        transparent: true,
        opacity: 0.14,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const shell = new THREE.Mesh(shellGeo, shellMat);
      bubble.add(shell);

      const glowMat = new THREE.SpriteMaterial({
        map: getGlowTexture(color),
        color: threeColor,
        transparent: true,
        opacity: 0.24,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const glow = new THREE.Sprite(glowMat);
      glow.scale.setScalar(6.8);
      glow.renderOrder = -1;
      bubble.add(glow);

      const haloMat = new THREE.MeshBasicMaterial({
        color: threeColor,
        transparent: true,
        opacity: 0,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const halo = new THREE.Mesh(haloGeo, haloMat);
      halo.rotation.x = Math.PI / 2;
      bubble.add(halo);

      bubble.userData = { pointId: point.id, baseScale: size, core, shell, glow, halo };
      group.add(bubble);

      [core, shell, glow, halo].forEach((part) => {
        part.userData.pointId = point.id;
        meshToId.current.set(part.id, point.id);
      });
      idToBubble.current.set(point.id, bubble);
    }
  }, [points, categoryColors, activeCategories]);

  // Presentation labels for category territories.
  useEffect(() => {
    const labelGroup = labelGroupRef.current;
    if (!labelGroup) return;

    while (labelGroup.children.length > 0) {
      const child = labelGroup.children[0];
      labelGroup.remove(child);
      disposeObject(child);
    }

    const clusters = new Map<string, { count: number; x: number; y: number; z: number }>();
    points.forEach((point) => {
      if (!activeCategories.has(point.category)) return;
      const current = clusters.get(point.category) || { count: 0, x: 0, y: 0, z: 0 };
      current.count += 1;
      current.x += point.x;
      current.y += point.y;
      current.z += point.z;
      clusters.set(point.category, current);
    });

    clusters.forEach((cluster, category) => {
      const color = categoryColors[category] || "#7c3aed";
      const label = new SpriteText(
        `${formatCategoryLabel(category)}\n${cluster.count} ${cluster.count === 1 ? "ad" : "ads"}`,
        compact ? 1.8 : 2.75,
        "#f8fafc"
      );
      label.position.set(
        cluster.x / cluster.count,
        cluster.y / cluster.count + (compact ? 6.5 : 8.5),
        cluster.z / cluster.count
      );
      label.renderOrder = 10;
      label.material.depthWrite = false;
      label.material.opacity = 0.82;
      label.backgroundColor = "rgba(6, 9, 14, 0.72)";
      label.borderColor = `${color}88`;
      label.borderWidth = 0.4;
      label.borderRadius = 3;
      label.padding = 3;
      labelGroup.add(label);
    });
  }, [points, activeCategories, categoryColors, compact]);

  // Highlight selected / hovered + draw connections
  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;

    const selectedPoint = selectedId ? points.find((p) => p.id === selectedId) : null;

    idToBubble.current.forEach((bubble, id) => {
      const point = points.find((p) => p.id === id);
      if (!point) return;
      const color = categoryColors[point.category] || "#7c3aed";
      const threeColor = getColor(color);
      const core = bubble.userData.core as THREE.Mesh;
      const shell = bubble.userData.shell as THREE.Mesh;
      const glow = bubble.userData.glow as THREE.Sprite;
      const halo = bubble.userData.halo as THREE.Mesh;
      const mat = core.material as THREE.MeshPhysicalMaterial;
      const shellMat = shell.material as THREE.MeshBasicMaterial;
      const glowMat = glow.material as THREE.SpriteMaterial;
      const haloMat = halo.material as THREE.MeshBasicMaterial;
      const isSelected = id === selectedId;
      const isHovered = id === hoveredId;

      if (isSelected) {
        mat.color.set(threeColor);
        mat.emissive.set(threeColor);
        mat.emissiveIntensity = 0.9;
        mat.opacity = 1.0;
        shellMat.opacity = 0.36;
        glowMat.opacity = 0.58;
        haloMat.opacity = 0.78;
        const s = POINT_SIZE_MAX * 2.25;
        bubble.scale.setScalar(s);
        bubble.userData.baseScale = s;
      } else if (isHovered) {
        mat.color.set(threeColor);
        mat.emissive.set(threeColor);
        mat.emissiveIntensity = 0.66;
        mat.opacity = 0.98;
        shellMat.opacity = 0.28;
        glowMat.opacity = 0.44;
        haloMat.opacity = 0.48;
        const s = POINT_SIZE_MAX * 1.55;
        bubble.scale.setScalar(s);
        bubble.userData.baseScale = s;
      } else {
        const dimmed = selectedId && point.category !== selectedPoint?.category;
        mat.color.set(threeColor);
        mat.emissive.set(threeColor);
        mat.emissiveIntensity = dimmed ? 0.07 : 0.28;
        mat.opacity = dimmed ? 0.22 : 0.86;
        shellMat.opacity = dimmed ? 0.04 : 0.14;
        glowMat.opacity = dimmed ? 0.04 : 0.22;
        haloMat.opacity = 0;
        const size = POINT_SIZE_BASE + Math.min(point.confidence, 1) * (POINT_SIZE_MAX - POINT_SIZE_BASE);
        bubble.scale.setScalar(size);
        bubble.userData.baseScale = size;
      }
    });

    // Draw connection lines from selected point to cluster neighbors
    const lineSeg = connectionLinesRef.current;
    if (!lineSeg) return;

    if (selectedPoint) {
      const sameCategory = points.filter(
        (p) => p.category === selectedPoint.category && p.id !== selectedPoint.id
      );
      const nearby = sameCategory
        .sort((a, b) => {
          const da = Math.sqrt((a.x - selectedPoint.x) ** 2 + (a.y - selectedPoint.y) ** 2 + (a.z - selectedPoint.z) ** 2);
          const db = Math.sqrt((b.x - selectedPoint.x) ** 2 + (b.y - selectedPoint.y) ** 2 + (b.z - selectedPoint.z) ** 2);
          return da - db;
        })
        .slice(0, 12);

      const linePositions: number[] = [];
      nearby.forEach((p) => {
        const dist = Math.sqrt(
          (p.x - selectedPoint.x) ** 2 +
          (p.y - selectedPoint.y) ** 2 +
          (p.z - selectedPoint.z) ** 2
        );
        if (dist < 42) {
          linePositions.push(selectedPoint.x, selectedPoint.y, selectedPoint.z);
          linePositions.push(p.x, p.y, p.z);
        }
      });

      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));
      lineSeg.geometry.dispose();
      lineSeg.geometry = geo;

      const lineMat = lineSeg.material as THREE.LineBasicMaterial;
      const catColor = getColor(categoryColors[selectedPoint.category] || "#7c3aed");
      lineMat.color.set(catColor);
      lineMat.opacity = 0.24;
    } else {
      const geo = new THREE.BufferGeometry();
      lineSeg.geometry.dispose();
      lineSeg.geometry = geo;
    }
  }, [selectedId, hoveredId, points, categoryColors]);

  // Smoothly frame a selected point without changing the underlying projection.
  useEffect(() => {
    if (!selectedId) return;
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    const point = points.find((p) => p.id === selectedId);
    if (!camera || !controls || !point) return;

    const startPos = camera.position.clone();
    const startTarget = controls.target.clone();
    const target = new THREE.Vector3(point.x, point.y, point.z);
    const endPos = target.clone().add(new THREE.Vector3(42, 28, 48).normalize().multiplyScalar(compact ? 78 : 62));
    const startTime = performance.now();
    const duration = 850;

    const animateCamera = () => {
      const t = Math.min((performance.now() - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      camera.position.lerpVectors(startPos, endPos, eased);
      controls.target.lerpVectors(startTarget, target, eased);
      controls.update();
      if (t < 1) cameraTweenRef.current = requestAnimationFrame(animateCamera);
    };

    cancelAnimationFrame(cameraTweenRef.current);
    cameraTweenRef.current = requestAnimationFrame(animateCamera);
    return () => cancelAnimationFrame(cameraTweenRef.current);
  }, [selectedId, points, compact]);

  // Raycasting
  const getIntersectedPoint = useCallback(
    (event: MouseEvent): ScatterPoint | null => {
      const camera = cameraRef.current;
      const group = groupRef.current;
      const el = containerRef.current;
      if (!camera || !group || !el) return null;

      const rect = el.getBoundingClientRect();
      mouse.current.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.current.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.current.setFromCamera(mouse.current, camera);
      raycaster.current.params.Points = { threshold: RAYCASTER_THRESHOLD };

      const intersects = raycaster.current.intersectObjects(group.children, true);
      if (intersects.length === 0) return null;

      const hit = intersects[0].object;
      const pid = meshToId.current.get(hit.id);
      if (!pid) return null;
      return points.find((p) => p.id === pid) || null;
    },
    [points]
  );

  const handleClick = useCallback(
    (event: MouseEvent) => {
      const point = getIntersectedPoint(event);
      if (point) {
        onPointClick(point);
      } else {
        onBackgroundClick?.();
      }
    },
    [getIntersectedPoint, onPointClick, onBackgroundClick]
  );

  const handleMouseMove = useCallback(
    (event: MouseEvent) => {
      const now = performance.now();
      if (now - hoverThrottle.current < 40) return;
      hoverThrottle.current = now;

      const point = getIntersectedPoint(event);
      const rect = containerRef.current?.getBoundingClientRect();
      onPointHover(
        point,
        point && rect ? { x: event.clientX - rect.left, y: event.clientY - rect.top } : undefined
      );
    },
    [getIntersectedPoint, onPointHover]
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener("click", handleClick);
    el.addEventListener("mousemove", handleMouseMove);
    return () => {
      el.removeEventListener("click", handleClick);
      el.removeEventListener("mousemove", handleMouseMove);
    };
  }, [handleClick, handleMouseMove]);

  return <div className="es-canvas-wrap" ref={containerRef} />;
}
