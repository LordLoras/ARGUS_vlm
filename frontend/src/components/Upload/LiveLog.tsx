import { useEffect, useRef } from "react";

export type LogLine = {
  ts: string;
  level: "info" | "ok" | "warn" | "rule";
  message: string;
};

export function LiveLog({ lines }: { lines: LogLine[] }) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines.length]);
  return (
    <div className="live-log" ref={ref}>
      {lines.length === 0 ? (
        <div className="ln">
          <span className="ts">--:--:--</span>
          <span className="lvl info">INFO</span>
          <span>Waiting for worker events…</span>
        </div>
      ) : (
        lines.map((ln, idx) => (
          <div className="ln" key={`${ln.ts}-${idx}`}>
            <span className="ts">{ln.ts}</span>
            <span className={`lvl ${ln.level}`}>{ln.level.toUpperCase()}</span>
            <span>{ln.message}</span>
          </div>
        ))
      )}
    </div>
  );
}
