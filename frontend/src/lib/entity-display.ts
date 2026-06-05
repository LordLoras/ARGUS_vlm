export function compactEvidenceText(value?: string | null, maxChars = 360) {
  const normalized = (value ?? "").replace(/\s+/g, " ").trim();
  if (!normalized) return "";

  const sentences = normalized.match(/[^.!?]+[.!?]+|[^.!?]+$/g) ?? [normalized];
  const compact: string[] = [];
  let previous = "";
  let previousKey = "";
  let suppressed = 0;

  for (const sentence of sentences) {
    const trimmed = sentence.trim();
    if (!trimmed) continue;
    const key = trimmed.toLowerCase();
    const normalizedKey = key.replace(/[^a-z0-9]+/g, " ").trim();
    if (key === previous || isRepeatedFragment(previousKey, normalizedKey)) {
      suppressed += 1;
      continue;
    }
    compact.push(trimmed);
    previous = key;
    previousKey = normalizedKey;
  }

  const suffix = suppressed
    ? ` (${suppressed.toLocaleString()} repeated sentence${suppressed === 1 ? "" : "s"} hidden)`
    : "";
  const joined = compact.join(" ");
  if (joined.length + suffix.length <= maxChars) return `${joined}${suffix}`;

  const trimAt = Math.max(0, maxChars - suffix.length - 1);
  return `${joined.slice(0, trimAt).trimEnd()}...${suffix}`;
}

function isRepeatedFragment(previous: string, next: string) {
  if (!previous || !next || Math.min(previous.length, next.length) < 12) return false;
  return previous.startsWith(next) || next.startsWith(previous);
}

export function shortSourceId(value?: string | null) {
  if (!value) return "No source id";
  if (value.startsWith("src_submitted_ad_")) {
    return value.replace("src_submitted_ad_", "submitted ad ");
  }
  if (value.startsWith("src_discovery_")) {
    return value.replace("src_discovery_", "discovery ");
  }
  return value;
}
