import type { AgentSession } from "../../lib/types";

const TOOL_META: Record<string, { label: string; desc: string }> = {
  list_ads: { label: "List Ads", desc: "Filter and browse ads by brand, category, status, or free text." },
  count_ads: { label: "Count Ads", desc: "Count matching ads with the same filter set." },
  get_ad: { label: "Get Ad", desc: "Fetch a single ad with classification, entities, and campaigns." },
  aggregate: { label: "Aggregate", desc: "Group ads by any dimension and return counts per group." },
  hybrid_search: { label: "Hybrid Search", desc: "Keyword + vector search with reciprocal rank fusion." },
  vector_similarity: { label: "Vector Similarity", desc: "Find ads similar to a seed ad by text or visual embeddings." },
  compare_ads: { label: "Compare Ads", desc: "Side-by-side comparison with similarity scores and field diffs." },
  list_campaigns: { label: "List Campaigns", desc: "Browse campaigns filtered by brand or text." },
  get_campaign: { label: "Get Campaign", desc: "Fetch a campaign with its assigned ads." },
  sql_readonly: { label: "SQL Query", desc: "Bounded read-only SELECT for questions the tools cannot cover." },
};

const TOOL_ORDER = Object.keys(TOOL_META);

export function ContextRail({
  session,
  toolCounts,
  toolsCalled
}: {
  session?: AgentSession | null;
  toolCounts?: Record<string, number>;
  toolsCalled?: number;
}) {
  const hasActiveTools = toolsCalled && toolsCalled > 0;
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
        <h4>{hasActiveTools ? "Tools used" : "Available tools"}</h4>
        <div className="tool-list">
          {TOOL_ORDER.map((name) => {
            const meta = TOOL_META[name];
            const count = toolCounts?.[name] ?? 0;
            const active = count > 0;
            return (
              <div className="tool-row" key={name} data-active={active || undefined} style={{ opacity: hasActiveTools ? (active ? 1 : 0.4) : 0.65 }}>
                <div className="tool-row-main">
                  <span className="name">{meta.label}</span>
                  <span className="tool-desc">{meta.desc}</span>
                </div>
                {active && <span className="calls">{count}</span>}
              </div>
            );
          })}
        </div>
      </section>

      <section className="context-section">
        <h4>Trust</h4>
        <div style={{ color: "var(--fg-mute)", fontSize: 11.5, lineHeight: 1.55 }}>
          All tools are read-only. The agent cannot mutate ads, campaigns, or
          classifications. Every tool call and result is appended to the session
          for audit.
        </div>
      </section>
    </aside>
  );
}
