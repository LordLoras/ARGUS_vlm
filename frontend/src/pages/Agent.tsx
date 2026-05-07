import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";

import { ChatInput } from "../components/Chat/ChatInput";
import { ContextRail } from "../components/Chat/ContextRail";
import { MessageList } from "../components/Chat/MessageList";
import { SessionList } from "../components/Chat/SessionList";
import type { ToolCard } from "../components/Chat/ToolCallCard";
import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api, streamAgentQuery } from "../lib/api-client";
import { CopyIcon } from "../lib/icons";
import type { AgentMessage, AgentSession, AgentStreamEvent } from "../lib/types";

export function Agent() {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  const [localMessages, setLocalMessages] = useState<AgentMessage[]>([]);
  const [tools, setTools] = useState<ToolCard[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const cleanupRef = useRef<(() => void) | null>(null);
  const health = useApiHealth();

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
  const usage = useQuery({
    queryKey: ["agent-usage"],
    queryFn: api.getAgentUsage,
    retry: false
  });

  const newSession = useMutation({
    mutationFn: api.createAgentSession,
    onSuccess: async (result) => {
      setActiveId(result.session_id);
      setLocalMessages([]);
      setTools([]);
      setDraft("");
      await queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
    }
  });

  const messages: AgentMessage[] = activeId
    ? session.data?.messages ?? localMessages
    : localMessages;

  const toolCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    tools.forEach((tool) => {
      counts[tool.name] = (counts[tool.name] ?? 0) + 1;
    });
    return counts;
  }, [tools]);

  const submit = (message: string) => {
    setLocalMessages((current) => [...current, { role: "user", content: message }]);
    if (!activeId) {
      setLocalMessages((current) => [
        ...current,
        {
          role: "assistant",
          content:
            "Phase 9 (`/api/agent/*`) is not implemented yet. This UI is wired and ready: it will stream tool calls, render their JSON, and roll up usage as soon as the backend lands."
        }
      ]);
      return;
    }
    setStreaming(true);
    setDraft("");
    cleanupRef.current = streamAgentQuery(activeId, message, handleStreamEvent);
  };

  function handleStreamEvent(event: AgentStreamEvent) {
    if (event.type === "token") setDraft((current) => current + event.text);
    if (event.type === "tool_call") {
      setTools((current) => [
        ...current,
        {
          id: `${event.name}-${current.length}`,
          name: event.name,
          args: event.args,
          status: "running"
        }
      ]);
    }
    if (event.type === "tool_result") {
      setTools((current) =>
        current.map((tool) =>
          tool.name === event.name && tool.status === "running"
            ? {
                ...tool,
                result: event.result ?? null,
                summary: event.summary ?? `${event.rows ?? 0} rows`,
                truncated: event.truncated,
                status: "done"
              }
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

  const stop = () => {
    cleanupRef.current?.();
    setStreaming(false);
  };

  const activeSession: AgentSession | undefined = activeId
    ? session.data?.session
    : undefined;

  const phase9Down = sessions.isError;

  return (
    <>
      <Topbar
        crumbs={["Intelligence", "Agent", activeSession?.title ?? "New chat"]}
        actions={
          <button className="btn btn-ghost btn-sm" disabled>
            <CopyIcon size={11} />
            <span>Share</span>
          </button>
        }
      />
      <ApiOfflineBanner offline={health.isError} />
      {phase9Down ? (
        <div
          className="row"
          style={{
            background: "var(--amber-bg)",
            color: "var(--amber)",
            borderBottom: "1px solid var(--border)",
            padding: "8px 16px",
            fontSize: 12
          }}
        >
          Phase 9 agent endpoints not implemented yet — this UI is ready and will activate when `/api/agent/*` lands.
        </div>
      ) : null}

      <div className="chat-layout">
        <SessionList
          sessions={sessions.data?.items ?? []}
          activeId={activeId}
          totalToday={usage.data?.today_tokens ?? null}
          onNew={() => newSession.mutate()}
          onSelect={(sessionId) => {
            setActiveId(sessionId);
            setLocalMessages([]);
            setTools([]);
            setDraft("");
          }}
        />

        <section className="chat-main">
          <div className="chat-header">
            <span className="session-title">
              {activeSession?.title ?? "New conversation"}
            </span>
            <span className="session-id">
              {activeSession?.id ?? "no session"} · gemma-3-12b · {tools.length} tool calls
            </span>
            {streaming ? (
              <span className="stream-state">
                <span className="dot" />
                streaming…
              </span>
            ) : null}
          </div>
          <MessageList
            messages={messages}
            tools={tools}
            draft={draft}
            streaming={streaming}
            onPrompt={submit}
          />
          <ChatInput
            disabled={false}
            streaming={streaming}
            onSubmit={submit}
            onStop={stop}
          />
        </section>

        <ContextRail
          session={activeSession}
          toolCounts={toolCounts}
          toolsCalled={tools.length}
        />
      </div>
    </>
  );
}
