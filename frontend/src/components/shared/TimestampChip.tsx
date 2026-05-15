import { formatTimestamp } from "../../lib/format";

export function TimestampChip({
  timeMs,
  onSeek
}: {
  timeMs?: number | null;
  onSeek?: (timeMs: number) => void;
}) {
  if (timeMs == null) return null;
  const label = formatTimestamp(timeMs);
  if (!onSeek) return <span className="ts-link">{label}</span>;
  return (
    <button
      type="button"
      className="ts-link"
      onClick={() => onSeek(timeMs)}
      title={`Show paused video at ${label}`}
    >
      {label}
    </button>
  );
}
