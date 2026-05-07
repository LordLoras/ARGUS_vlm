import { cn } from "../../lib/utils";

export function ConfidenceBar({ value }: { value?: number | null }) {
  if (value == null) return <span className="obs-empty">—</span>;
  const pct = Math.max(0, Math.min(1, value));
  const tone = pct >= 0.85 ? "high" : pct >= 0.7 ? "med" : "low";
  return (
    <div className={cn("conf", tone)}>
      <div className="conf-bar">
        <span style={{ width: `${pct * 100}%` }} />
      </div>
      <span>{pct.toFixed(2)}</span>
    </div>
  );
}
