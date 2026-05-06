import { Plus, Trash2 } from "lucide-react";

import { relativeTime } from "../../lib/format";
import type { AgentSession } from "../../lib/types";
import { Button } from "../ui/Button";

export function SessionList({
  sessions,
  activeId,
  onNew,
  onSelect,
  onDelete
}: {
  sessions: AgentSession[];
  activeId?: string | null;
  onNew: () => void;
  onSelect: (sessionId: string) => void;
  onDelete: (sessionId: string) => void;
}) {
  return (
    <aside className="w-72 border-r border-border bg-surface p-4">
      <Button variant="primary" className="w-full" onClick={onNew}>
        <Plus className="h-4 w-4" />
        New chat
      </Button>
      <div className="mt-4 space-y-2">
        {sessions.length === 0 && <p className="text-sm text-muted-foreground">No conversations yet · click + New chat to start</p>}
        {sessions.map((session) => (
          <button
            key={session.id}
            onClick={() => onSelect(session.id)}
            className={`group flex w-full items-center gap-2 rounded-md border-l-2 px-3 py-2 text-left transition ${
              activeId === session.id ? "border-violet-400 bg-violet-500/10" : "border-transparent hover:bg-muted"
            }`}
          >
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm">{session.title || "Untitled chat"}</div>
              <div className="mt-1 text-xs text-muted-foreground">{relativeTime(session.updated_at || session.created_at)}</div>
            </div>
            <span className="font-mono text-xs text-muted-foreground">{session.token_count ?? 0} tok</span>
            <Trash2
              className="hidden h-4 w-4 text-muted-foreground group-hover:block"
              onClick={(event) => {
                event.stopPropagation();
                onDelete(session.id);
              }}
            />
          </button>
        ))}
      </div>
    </aside>
  );
}
