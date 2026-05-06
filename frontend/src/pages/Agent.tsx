import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { ChatInput } from "../components/Chat/ChatInput";
import { MessageList } from "../components/Chat/MessageList";
import { SessionList } from "../components/Chat/SessionList";
import type { ToolCard } from "../components/Chat/ToolCallCard";
import { api, streamAgentQuery } from "../lib/api-client";
import type { AgentMessage, AgentStreamEvent } from "../lib/types";

export function Agent() {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [localMessages, setLocalMessages] = useState<AgentMessage[]>([]);
  const [tools, setTools] = useState<ToolCard[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);

  const sessions = useQuery({
    queryKey: ["agent-sessions"],
    queryFn: api.listAgentSessions,
    retry: false
  });
  const session = useQuery({
    queryKey: ["agent-session", activeId],
    queryFn: () => api.getAgentSession(activeId ?? ""),
    enabled: Boolean(activeId),
    retry: false
  });

  const newSession = useMutation({
    mutationFn: api.createAgentSession,
    onSuccess: async (result) => {
      setActiveId(result.session_id);
      await queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
    }
  });
  const deleteSession = useMutation({
    mutationFn: api.deleteAgentSession,
    onSuccess: async () => {
      setActiveId(null);
      await queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
    }
  });

  const messages = activeId ? session.data?.messages ?? localMessages : localMessages;

  function submit(message: string) {
    setLocalMessages((current) => [...current, { role: "user", content: message }]);
    setDraft("");
    setTools([]);
    if (!activeId) {
      setLocalMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: "Agent endpoints are not available yet. Phase 9 will add the read-only tool loop this page consumes."
        }
      ]);
      return;
    }
    setStreaming(true);
    cleanupRef.current = streamAgentQuery(activeId, message, handleStreamEvent);
  }

  function handleStreamEvent(event: AgentStreamEvent) {
    if (event.type === "token") setDraft((current) => current + event.text);
    if (event.type === "tool_call") {
      setTools((current) => [...current, { id: `${event.name}-${current.length}`, name: event.name, args: event.args }]);
    }
    if (event.type === "tool_result") {
      setTools((current) =>
        current.map((tool) =>
          tool.name === event.name
            ? { ...tool, result: event.result ?? event, summary: event.summary ?? `${event.rows ?? 0} rows`, truncated: event.truncated }
            : tool
        )
      );
    }
    if (event.type === "done") {
      setStreaming(false);
      setLocalMessages((current) => [...current, { role: "assistant", content: draft }]);
      setDraft("");
    }
    if (event.type === "error") {
      setStreaming(false);
      setLocalMessages((current) => [...current, { role: "assistant", content: event.message }]);
    }
  }

  function stop() {
    cleanupRef.current?.();
    setStreaming(false);
  }

  return (
    <div className="h-[calc(100vh-8.5rem)] overflow-hidden rounded-lg border border-border bg-background">
      <div className="flex h-full">
        <SessionList
          sessions={sessions.data?.items ?? []}
          activeId={activeId}
          onNew={() => newSession.mutate()}
          onSelect={(sessionId) => {
            setActiveId(sessionId);
            setLocalMessages([]);
            setTools([]);
            setDraft("");
          }}
          onDelete={(sessionId) => deleteSession.mutate(sessionId)}
        />
        <section className="flex min-w-0 flex-1 flex-col">
          {sessions.isError && (
            <div className="border-b border-amber-400/20 bg-amber-500/10 px-4 py-2 text-sm text-amber-100">
              Agent API is not implemented yet; this UI is ready for Phase 9 endpoints.
            </div>
          )}
          <div className="scrollbar-thin min-h-0 flex-1 overflow-auto">
            <MessageList messages={messages} tools={tools} draft={draft} onPrompt={submit} />
          </div>
          <ChatInput disabled={false} streaming={streaming} onSubmit={submit} onStop={stop} />
        </section>
      </div>
    </div>
  );
}
