import { useRef, useEffect, useCallback, useState } from "react";
import * as THREE from "three";
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
}

const POINT_SIZE_BASE = 0.55;
const POINT_SIZE_MAX = 1.3;
const BG_COLOR = 0x06070a;
const RAYCASTER_THRESHOLD = 2.0;

const sphereGeo = new THREE.SphereGeometry(1, 16, 12);

const colorCache = new Map<string, THREE.Color>();
function getColor(hex: string): THREE.Color {
  let c = colorCache.get(hex);
  if (!c) {
    c = new THREE.Color(hex);
    colorCache.set(hex, c);
  }
  return c;
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
  const idToMesh = useRef(new Map<string, THREE.Mesh>());
  const animFrame = useRef(0);
  const hoverThrottle = useRef(0);
  const clockRef = useRef(new THREE.Clock());
  const cameraTweenRef = useRef(0);
  const connectionLinesRef = useRef<THREE.LineSegments | null>(null);
  const dustRef = useRef<THREE.Points | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(BG_COLOR);
    scene.fog = new THREE.FogExp2(BG_COLOR, 0.0025);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(50, el.clientWidth / el.clientHeight, 0.1, 800);
    camera.position.set(70, 50, 70);
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
      0.35,
      0.6,
      0.82
    );
    composer.addPass(bloom);
    composerRef.current = composer;

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.minDistance = 15;
    controls.maxDistance = 200;
    controls.target.set(0, 0, 0);
    controls.maxPolarAngle = Math.PI * 0.85;
    controlsRef.current = controls;

    // Ambient + directional
    scene.add(new THREE.AmbientLight(0xffffff, 0.4));
    const dirLight = new THREE.DirectionalLight(0x9ca3af, 0.3);
    dirLight.position.set(30, 60, 40);
    scene.add(dirLight);

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

    const clock = clockRef.current;

    const animate = () => {
      animFrame.current = requestAnimationFrame(animate);
      const t = clock.getElapsedTime();

      controls.update();

      // Breathing animation on points
      group.children.forEach((child, i) => {
        if (child.userData.pointId) {
          const base = child.userData.baseScale || 1;
          const breath = 1 + Math.sin(t * 0.8 + i * 0.1) * 0.025;
          child.scale.setScalar(base * breath);
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
  }, []);

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
      if (((child as THREE.Mesh).material as THREE.Material).dispose) {
        ((child as THREE.Mesh).material as THREE.Material).dispose();
      }
    }
    meshToId.current.clear();
    idToMesh.current.clear();

    for (const point of points) {
      if (!activeCategories.has(point.category)) continue;

      const color = categoryColors[point.category] || "#7c3aed";
      const size = POINT_SIZE_BASE + Math.min(point.confidence, 1) * (POINT_SIZE_MAX - POINT_SIZE_BASE);
      const threeColor = getColor(color);

      // Core point
      const mat = new THREE.MeshStandardMaterial({
        color: threeColor,
        emissive: threeColor,
        emissiveIntensity: 0.3,
        roughness: 0.4,
        metalness: 0.1,
        transparent: true,
        opacity: 0.88,
      });
      const mesh = new THREE.Mesh(sphereGeo, mat);
      mesh.position.set(point.x, point.y, point.z);
      mesh.scale.setScalar(size);
      mesh.userData = { pointId: point.id, baseScale: size };
      group.add(mesh);

      meshToId.current.set(mesh.id, point.id);
      idToMesh.current.set(point.id, mesh);
    }
  }, [points, categoryColors, activeCategories]);

  // Highlight selected / hovered + draw connections
  useEffect(() => {
    const group = groupRef.current;
    if (!group) return;

    const selectedPoint = selectedId ? points.find((p) => p.id === selectedId) : null;

    idToMesh.current.forEach((mesh, id) => {
      const point = points.find((p) => p.id === id);
      if (!point) return;
      const color = categoryColors[point.category] || "#7c3aed";
      const threeColor = getColor(color);
      const mat = mesh.material as THREE.MeshStandardMaterial;
      const isSelected = id === selectedId;
      const isHovered = id === hoveredId;

      if (isSelected) {
        mat.color.set(threeColor);
        mat.emissive.set(threeColor);
        mat.emissiveIntensity = 0.8;
        mat.opacity = 1.0;
        const s = POINT_SIZE_MAX * 2.4;
        mesh.scale.setScalar(s);
        mesh.userData.baseScale = s;
      } else if (isHovered) {
        mat.color.set(threeColor);
        mat.emissive.set(threeColor);
        mat.emissiveIntensity = 0.6;
        mat.opacity = 0.95;
        const s = POINT_SIZE_MAX * 1.6;
        mesh.scale.setScalar(s);
        mesh.userData.baseScale = s;
      } else {
        const dimmed = selectedId && point.category !== selectedPoint?.category;
        mat.color.set(threeColor);
        mat.emissive.set(threeColor);
        mat.emissiveIntensity = dimmed ? 0.08 : 0.3;
        mat.opacity = dimmed ? 0.2 : 0.78;
        const size = POINT_SIZE_BASE + Math.min(point.confidence, 1) * (POINT_SIZE_MAX - POINT_SIZE_BASE);
        mesh.scale.setScalar(size);
        mesh.userData.baseScale = size;
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
        if (dist < 30) {
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
      lineMat.opacity = 0.15;
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
    const endPos = target.clone().add(new THREE.Vector3(42, 28, 48).normalize().multiplyScalar(62));
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
  }, [selectedId, points]);

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

      const intersects = raycaster.current.intersectObjects(group.children, false);
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
