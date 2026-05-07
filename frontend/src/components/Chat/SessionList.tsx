import { useState } from "react";

import { relativeTime } from "../../lib/format";
import { PlusIcon, SearchIcon } from "../../lib/icons";
import type { AgentSession } from "../../lib/types";

export function SessionList({
  sessions,
  activeId,
  totalToday,
  onNew,
  onSelect
}: {
  sessions: AgentSession[];
  activeId?: string | null;
  totalToday?: number | null;
  onNew: () => void;
  onSelect: (sessionId: string) => void;
}) {
  const [filter, setFilter] = useState("");
  const filtered = sessions.filter(
    (s) =>
      !filter ||
      (s.title ?? "").toLowerCase().includes(filter.toLowerCase()) ||
      s.id.toLowerCase().includes(filter.toLowerCase())
  );
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
              <div className="preview">{session.title || "Untitled chat"}</div>
              <div className="meta">
                <span>{relativeTime(session.updated_at || session.created_at)}</span>
                <span>·</span>
                <span>{session.token_count ?? 0} tok</span>
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
        <span className="health-meta">
          {totalToday != null ? `${totalToday} tok today` : "$0.00 (local)"}
        </span>
      </div>
    </aside>
  );
}
