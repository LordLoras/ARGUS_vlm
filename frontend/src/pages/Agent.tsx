import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ToolCard } from "../components/Chat/ToolCallCard";
import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api, streamAgentQuery } from "../lib/api-client";
import { CopyIcon, SearchIcon, LayersIcon, FilmIcon, FlowIcon } from "../lib/icons";
import type { AgentMessage, AgentSession, AgentStreamEvent } from "../lib/types";

import { ChatInput } from "../components/Chat/ChatInput";
import { ContextRail } from "../components/Chat/ContextRail";
import { MessageList } from "../components/Chat/MessageList";
import { SessionList } from "../components/Chat/SessionList";

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
  const scrollRef = useRef<HTMLDivElement | null>(null);

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
        break;
      case "error":
        setStreamMessages((current) => {
          if (event.payload.message && !current.some(m => m.role === "assistant")) {
            return [
              ...current,
              {
                role: "assistant",
                content: `Error: ${event.payload.message}`
              }
            ];
          }
          return current;
        });
        break;
      case "done": {
        const doneSid = (event.payload.session_id as string) || activeId || "";
        setStreaming(false);
        cleanupRef.current = null;
        void queryClient
          .invalidateQueries({ queryKey: ["agent-session", doneSid] })
          .then(() => setStreamMessages([]));
        void queryClient.invalidateQueries({ queryKey: ["agent-sessions"] });
        requestAnimationFrame(() => {
          if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
          }
        });
        break;
      }
    }
  };

  const handleStreamEventRef = useRef(handleStreamEvent);
  handleStreamEventRef.current = handleStreamEvent;

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
    cleanupRef.current = streamAgentQuery(
      sid,
      message,
      (event) => handleStreamEventRef.current(event)
    );
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
          {activeId ? (
            <>
              <div className="chat-header">
                <span className="session-title">{sessionLabel(activeSession)}</span>
                <span className="session-id">
                  {activeSession?.id ?? "no session"} · ARGUS · {tools.length} tool calls
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
                scrollRef={scrollRef}
              />
            </>
          ) : (
            <div className="agent-landing">
              <div className="agent-landing-glow" />
              <div className="agent-landing-content">
                <div className="agent-landing-badge">ARGUS v0.1</div>
                <h1 className="agent-landing-title">
                  Ad Retrieval, <span className="grdt">Graphing</span> &amp; Understanding System
                </h1>
                <p className="agent-landing-sub">
                  Natural-language query engine for your ad library. Ask questions, compare
                  campaigns, and discover patterns across brands, categories, and time.
                </p>
                <div className="agent-landing-cards">
                  <div className="agent-card">
                    <SearchIcon size={16} />
                    <span>Search &amp; filter by brand, category, product type, or free text</span>
                  </div>
                  <div className="agent-card">
                    <LayersIcon size={16} />
                    <span>Compare ads side-by-side across multiple dimensions</span>
                  </div>
                  <div className="agent-card">
                    <FilmIcon size={16} />
                    <span>Discover similar creatives by visual &amp; semantic similarity</span>
                  </div>
                  <div className="agent-card">
                    <FlowIcon size={16} />
                    <span>Aggregate and count — "how many SUV ads this month?"</span>
                  </div>
                </div>
                <div className="agent-landing-prompt">
                  <span className="agent-landing-prompt-icon">⟶</span>
                  <button
                    className="agent-landing-prompt-btn"
                    onClick={() => {
                      submit("Show me all ads grouped by category");
                    }}
                  >
                    Show me all ads grouped by category
                  </button>
                  <button
                    className="agent-landing-prompt-btn"
                    onClick={() => {
                      submit("Compare the two most recent automotive ads");
                    }}
                  >
                    Compare the two most recent automotive ads
                  </button>
                  <button
                    className="agent-landing-prompt-btn"
                    onClick={() => {
                      submit("How many SUV ads do I have?");
                    }}
                  >
                    How many SUV ads do I have?
                  </button>
                </div>
              </div>
            </div>
          )}
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
