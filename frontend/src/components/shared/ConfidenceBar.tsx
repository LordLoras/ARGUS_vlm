import { formatPercent } from "../../lib/format";

export function ConfidenceBar({ value }: { value?: number | null }) {
  const width = Math.max(0, Math.min(100, Math.round((value ?? 0) * 100)));
  return (
    <div className="flex min-w-28 items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-accent" style={{ width: `${width}%` }} />
      </div>
      <span className="w-9 text-right font-mono text-xs text-muted-foreground">{formatPercent(value)}</span>
    </div>
  );
}
