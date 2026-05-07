import { useState } from "react";

import { relativeTime } from "../../lib/format";
import { PlusIcon, SearchIcon } from "../../lib/icons";
import type { AgentSession } from "../../lib/types";

function sessionLabel(session: AgentSession): string {
  return session.user_label || `Chat ${session.id.replace(/^agent_/, "").slice(0, 6)}`;
}

export function SessionList({
  sessions,
  activeId,
  onNew,
  onSelect
}: {
  sessions: AgentSession[];
  activeId?: string | null;
  onNew: () => void;
  onSelect: (sessionId: string) => void;
}) {
  const [filter, setFilter] = useState("");
  const filtered = sessions.filter((s) => {
    if (!filter) return true;
    const needle = filter.toLowerCase();
    return (
      sessionLabel(s).toLowerCase().includes(needle) ||
      s.id.toLowerCase().includes(needle)
    );
  });
  return (
    <aside className="chat-sessions">
      <div className="sessions-head">
        <button className="btn btn-primary" onClick={onNew}>
          <PlusIcon size={11} />
          <span>New chat</span>
        </button>
        <div className="row" style={{ gap: 6 }}>
          <SearchIcon size={11} style={{ color: "var(--fg-quiet)" }} />
          <input
            className="input"
            placeholder="Search sessions"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>
      </div>
      <div className="sessions-list">
        {filtered.length === 0 ? (
          <div className="obs-empty" style={{ padding: 14 }}>
            No sessions yet — click New chat.
          </div>
        ) : (
          filtered.map((session) => (
            <div
              key={session.id}
              className={`session-item ${activeId === session.id ? "active" : ""}`}
              onClick={() => onSelect(session.id)}
            >
              <div className="preview">{sessionLabel(session)}</div>
              <div className="meta">
                <span>{relativeTime(session.created_at)}</span>
                <span>·</span>
                <span className="session-id-meta">{session.id}</span>
              </div>
            </div>
          ))
        )}
      </div>
      <div
        className="sidebar-footer"
        style={{ borderTop: "1px solid var(--border)", borderBottom: 0 }}
      >
        <span>{sessions.length} sessions</span>
        <span className="health-meta">local</span>
      </div>
    </aside>
  );
}
