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
    "get_ad",
    "list_campaigns",
    "get_campaign",
    "aggregate",
    "hybrid_search",
    "vector_similarity",
    "compare_ads",
    "sql_readonly"
  ];
  return (
    <aside className="chat-context">
      <section className="context-section">
        <h4>Session</h4>
        <div className="usage-grid">
          <div className="usage-cell">
            <div className="label">Tool calls</div>
            <div className="val">{toolsCalled ?? 0}</div>
            <div className="sub">this turn</div>
          </div>
          <div className="usage-cell">
            <div className="label">Started</div>
            <div className="val" style={{ fontSize: 11 }}>
              {session?.created_at
                ? new Date(session.created_at).toLocaleTimeString()
                : "—"}
            </div>
            <div className="sub">{session?.id ?? "no session"}</div>
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
        <h4>Notes</h4>
        <div style={{ color: "var(--fg-mute)", fontSize: 11.5, lineHeight: 1.55 }}>
          The agent only reads the local SQLite database. It cannot mutate ads,
          campaigns, or classifications. Every tool call and result is appended
          to the session for audit.
        </div>
      </section>
    </aside>
  );
}
