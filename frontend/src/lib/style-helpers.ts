/** Small helpers shared by table thumbnails and other visual cues. */
export function deriveSeed(adId: string): { seedA: string; seedB: string } {
  const palette = [
    ["#3b1a4a", "#1a2a3d"],
    ["#1a3a3a", "#2a4a5a"],
    ["#2a2030", "#1a1a30"],
    ["#3b1a3a", "#2a1a2a"],
    ["#1a3a1a", "#2a4a2a"],
    ["#3a2a1a", "#4a3a2a"],
    ["#3a1a2a", "#2a1a3a"],
    ["#1a2a4a", "#2a3a5a"],
    ["#1a3a4a", "#2a4a3a"],
    ["#3a3a1a", "#4a3a2a"],
    ["#1a3a2a", "#2a4a3a"]
  ];
  let hash = 0;
  for (let i = 0; i < adId.length; i += 1) hash = (hash * 31 + adId.charCodeAt(i)) >>> 0;
  const [a, b] = palette[hash % palette.length];
  return { seedA: a, seedB: b };
}

export function aspectFromDims(width?: number | null, height?: number | null): string | undefined {
  if (!width || !height) return undefined;
  const ratio = width / height;
  if (Math.abs(ratio - 16 / 9) < 0.05) return "16:9";
  if (Math.abs(ratio - 9 / 16) < 0.05) return "9:16";
  if (Math.abs(ratio - 1) < 0.05) return "1:1";
  if (Math.abs(ratio - 4 / 5) < 0.05) return "4:5";
  if (Math.abs(ratio - 4 / 3) < 0.05) return "4:3";
  return `${width}×${height}`;
}
