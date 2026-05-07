import type { AgentSession } from "../../lib/types";

export function ContextRail({
  session,
  toolCounts,
  toolsCalled
}: {
  session?: AgentSession | null;
  toolCounts?: Record<string, number>;
  toolsCalled?: number;
}) {
  const known = [
    "list_ads",
    "count_ads",
    "get_campaign",
    "hybrid_search",
    "vector_similarity",
    "compare_ads",
    "aggregate",
    "sql_readonly"
  ];
  return (
    <aside className="chat-context">
      <section className="context-section">
        <h4>Session usage</h4>
        <div className="usage-grid">
          <div className="usage-cell">
            <div className="label">Input tokens</div>
            <div className="val">{session?.token_count ?? 0}</div>
            <div className="sub">since start</div>
          </div>
          <div className="usage-cell">
            <div className="label">Output tokens</div>
            <div className="val">—</div>
            <div className="sub">phase 9</div>
          </div>
          <div className="usage-cell">
            <div className="label">Tool calls</div>
            <div className="val">{toolsCalled ?? 0}</div>
            <div className="sub">this session</div>
          </div>
          <div className="usage-cell">
            <div className="label">Latency avg</div>
            <div className="val">—</div>
            <div className="sub">phase 9</div>
          </div>
        </div>
      </section>

      <section className="context-section">
        <h4>Tools called</h4>
        <div className="tool-list">
          {known.map((name) => (
            <div className="tool-row" key={name} style={{ opacity: toolCounts?.[name] ? 1 : 0.45 }}>
              <span className="name">{name}</span>
              <span className="calls">{toolCounts?.[name] ?? 0}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="context-section">
        <h4>Active filters in scope</h4>
        <div className="pill-row" style={{ gap: 6 }}>
          <span className="obs-tag">all ads</span>
          <span className="obs-tag">last 30d</span>
        </div>
      </section>

      <section className="context-section">
        <h4>Daily usage</h4>
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: 1,
            height: 36
          }}
        >
          {Array.from({ length: 24 }).map((_, idx) => {
            const v = (Math.sin(idx * 0.6) + 1.4) / 2.6;
            return (
              <div
                key={idx}
                style={{
                  flex: 1,
                  height: `${Math.max(2, v * 36)}px`,
                  background:
                    "linear-gradient(180deg, var(--accent-2), var(--accent-bg))",
                  borderRadius: 1
                }}
              />
            );
          })}
        </div>
      </section>
    </aside>
  );
}
