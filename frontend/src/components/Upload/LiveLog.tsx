import { useEffect, useRef } from "react";

export type LogLevel = "info" | "ok" | "warn" | "rule";

export type LogLine = {
  ts: string;
  level: LogLevel;
  message: string;
};

const LEVEL_STYLES: Record<LogLevel, { color: string; bg: string }> = {
  info: { color: "var(--sky)", bg: "rgba(56,189,248,0.08)" },
  ok: { color: "var(--emerald)", bg: "rgba(52,211,153,0.08)" },
  warn: { color: "var(--amber)", bg: "rgba(251,191,36,0.08)" },
  rule: { color: "var(--violet)", bg: "rgba(139,92,246,0.08)" },
};

export function LiveLog({ lines }: { lines: LogLine[] }) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines.length]);

  return (
    <div className="ll-wrap">
      <div className="ll-bar">
        <span className="ll-bar-dot" style={{ background: "#f87171" }} />
        <span className="ll-bar-dot" style={{ background: "#fbbf24" }} />
        <span className="ll-bar-dot" style={{ background: "#34d399" }} />
        <span className="ll-bar-label">pipeline log</span>
      </div>
      <div className="ll-body" ref={ref}>
        {lines.length === 0 ? (
          <div className="ll-line">
            <span className="ll-ts">--:--:--</span>
            <span className="ll-lvl" style={{ color: "var(--fg-quiet)" }}>──</span>
            <span className="ll-msg" style={{ color: "var(--fg-quiet)" }}>
              Waiting for pipeline events…
            </span>
          </div>
        ) : (
          lines.map((ln, idx) => {
            const st = LEVEL_STYLES[ln.level];
            return (
              <div
                className="ll-line"
                key={`${ln.ts}-${idx}`}
                style={{ background: idx === lines.length - 1 ? st.bg : "transparent" }}
              >
                <span className="ll-ts">{ln.ts}</span>
                <span className="ll-lvl" style={{ color: st.color }}>{ln.level.toUpperCase()}</span>
                <span className="ll-msg">{ln.message}</span>
              </div>
            );
          })
        )}
        <div className="ll-cursor">▌</div>
      </div>
    </div>
  );
}
