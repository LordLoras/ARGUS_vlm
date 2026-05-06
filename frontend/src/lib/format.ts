export function formatDuration(ms?: number | null) {
  if (!ms) return "-";
  const seconds = Math.round(ms / 1000);
  const min = Math.floor(seconds / 60);
  const sec = seconds % 60;
  return `${min}:${sec.toString().padStart(2, "0")}`;
}

export function formatTimestamp(ms?: number | null) {
  if (ms == null) return "-";
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const millis = ms % 1000;
  return `${minutes}:${seconds.toString().padStart(2, "0")}.${millis.toString().padStart(3, "0")}`;
}

export function relativeTime(value?: string | null) {
  if (!value) return "-";
  const then = new Date(value).getTime();
  if (Number.isNaN(then)) return value;
  const delta = Date.now() - then;
  const minutes = Math.round(delta / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

export function filePathToDataUrl(path?: string | null) {
  if (!path) return "";
  const normalized = path.replace(/\\/g, "/");
  const dataIndex = normalized.lastIndexOf("/data/");
  if (dataIndex >= 0) return normalized.slice(dataIndex);
  if (normalized.startsWith("data/")) return `/${normalized}`;
  return normalized;
}

export function formatPercent(value?: number | null) {
  if (value == null) return "-";
  return `${Math.round(value * 100)}%`;
}
