import { Sparkline } from "../shared/Sparkline";

export type StatCell = {
  label: string;
  value: string;
  delta?: string;
  sub?: string;
  sparkValues: number[];
  sparkColor?: string;
  sensitive?: boolean;
};

export function StatStrip({ stats }: { stats: StatCell[] }) {
  return (
    <div
      className="stat-strip"
      style={{ gridTemplateColumns: `repeat(${stats.length}, 1fr)` }}
    >
      {stats.map((s) => (
        <div key={s.label} className={`stat ${s.sensitive ? "sensitive" : ""}`}>
          <div className="stat-label">{s.label}</div>
          <div className="stat-value">
            {s.value}
            {s.delta ? <span className="delta">{s.delta}</span> : null}
            {s.sub ? <span className="delta">{s.sub}</span> : null}
          </div>
          <div className="stat-spark">
            <Sparkline values={s.sparkValues} color={s.sparkColor ?? "var(--accent-2)"} />
          </div>
        </div>
      ))}
    </div>
  );
}
