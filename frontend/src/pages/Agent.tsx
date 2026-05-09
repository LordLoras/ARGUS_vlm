import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

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

type RenderedMessage = { role: "user" | "assistant"; content: string };

function sessionLabel(session: AgentSession | undefined | null): string {
  if (!session) return "New conversation";
  return session.user_label || `Chat ${session.id.replace(/^agent_/, "").slice(0, 6)}`;
}

function projectMessages(messages: AgentMessage[] | undefined): RenderedMessage[] {
  if (!messages) return [];
  return messages
    .filter((m) => (m.role === "user" || m.role === "assistant") && m.content)
    .map((m) => ({ role: m.role as "user" | "assistant", content: m.content ?? "" }));
}

export function Agent() {
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);
  // Live messages appended from SSE `message` events during the current turn.
  // Server is the source of truth; we render these on top of session.data?.messages
  // until the loop reports `done`, at which point we refetch and clear.
  const [streamMessages, setStreamMessages] = useState<RenderedMessage[]>([]);
  const [tools, setTools] = useState<ToolCard[]>([]);
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

  const newSession = useMutation({
    mutationFn: api.createAgentSession,
    onSuccess: async (result) => {
      setActiveId(result.session_id);
      setStreamMessages([]);
      setTools([]);
      await queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
    }
  });

  const deleteSession = useMutation({
    mutationFn: (sessionId: string) => api.deleteAgentSession(sessionId),
    onSuccess: async (_result, sessionId) => {
      if (activeId === sessionId) {
        setActiveId(null);
        setStreamMessages([]);
        setTools([]);
      }
      await queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
    }
  });

  // Cancel an in-flight stream on unmount.
  useEffect(() => {
    return () => {
      cleanupRef.current?.();
    };
  }, []);

  const serverMessages = useMemo(
    () => projectMessages(session.data?.messages),
    [session.data?.messages]
  );
  // While streaming we show server history + this turn's stream events.
  // After the turn ends and we refetch, server has everything → drop stream.
  const messages: RenderedMessage[] =
    streaming || streamMessages.length
      ? [...serverMessages, ...streamMessages]
      : serverMessages;

  const toolCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    tools.forEach((tool) => {
      counts[tool.name] = (counts[tool.name] ?? 0) + 1;
    });
    return counts;
  }, [tools]);

  const handleStreamEvent = (event: AgentStreamEvent) => {
    // eslint-disable-next-line no-console
    console.debug("[agent] event", event);
    switch (event.type) {
      case "session":
        break;
      case "message":
        setStreamMessages((current) => [
          ...current,
          {
            role: event.payload.role,
            content: event.payload.content
          }
        ]);
        break;
      case "tool_call":
        setTools((current) => [
          ...current,
          {
            id: event.payload.id,
            name: event.payload.name,
            args: event.payload.arguments,
            status: "running"
          }
        ]);
        break;
      case "tool_result":
        setTools((current) =>
          current.map((tool) =>
            tool.id === event.payload.id
              ? {
                  ...tool,
                  result: event.payload.data ?? null,
                  summary:
                    event.payload.error ??
                    `${event.payload.row_count ?? 0} rows${
                      event.payload.truncated ? " (truncated)" : ""
                    }`,
                  truncated: event.payload.truncated,
                  status: event.payload.ok ? "done" : "failed"
                }
              : tool
          )
        );
        break;
      case "final":
      case "error":
        // Both events carry text already delivered via a prior `message`
        // event in this turn — nothing additional to render.
        // If error, ensure we have content to show
        if (event.type === "error" && event.payload.message && !streamMessages.some(m => m.role === "assistant")) {
          setStreamMessages((current) => [
            ...current,
            {
              role: "assistant",
              content: `Error: ${event.payload.message}`
            }
          ]);
        }
        break;
      case "done":
        setStreaming(false);
        cleanupRef.current = null;
        // Server has the persisted user + assistant rows; refetch and drop the
        // local stream copies so we don't double-render.
        void queryClient
          .invalidateQueries({ queryKey: ["agent-session", activeId] })
          .then(() => setStreamMessages([]));
        void queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
        break;
    }
  };

  const submit = async (message: string) => {
    if (!message.trim() || streaming) return;

    let sid = activeId;
    if (!sid) {
      try {
        const created = await api.createAgentSession();
        sid = created.session_id;
        setActiveId(sid);
        await queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
      } catch (err) {
        const text = err instanceof Error ? err.message : String(err);
        setStreamMessages((current) => [
          ...current,
          { role: "user", content: message },
          { role: "assistant", content: `Failed to start session: ${text}` }
        ]);
        return;
      }
    }

    setStreaming(true);
    setTools([]);
    cleanupRef.current = streamAgentQuery(sid, message, handleStreamEvent);
  };

  const stop = () => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    setStreaming(false);
  };

  const activeSession: AgentSession | undefined = activeId
    ? session.data?.session
    : undefined;

  const apiOffline = sessions.isError;

  return (
    <>
      <Topbar
        crumbs={["Intelligence", "Agent", sessionLabel(activeSession) ?? "New chat"]}
        actions={
          <button className="btn btn-ghost btn-sm" disabled>
            <CopyIcon size={11} />
            <span>Share</span>
          </button>
        }
      />
      <ApiOfflineBanner offline={health.isError || apiOffline} />

      <div className="chat-layout">
        <SessionList
          sessions={sessions.data?.items ?? []}
          activeId={activeId}
          onNew={() => newSession.mutate()}
          onSelect={(sessionId) => {
            setActiveId(sessionId);
            setStreamMessages([]);
            setTools([]);
          }}
          onDelete={(sessionId) => deleteSession.mutate(sessionId)}
        />

        <section className="chat-main">
          <div className="chat-header">
            <span className="session-title">{sessionLabel(activeSession)}</span>
            <span className="session-id">
              {activeSession?.id ?? "no session"} · gemma · {tools.length} tool calls
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
