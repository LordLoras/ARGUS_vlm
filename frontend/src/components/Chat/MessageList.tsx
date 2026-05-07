import type { AgentMessage } from "../../lib/types";
import { ToolCallCard, type ToolCard } from "./ToolCallCard";

const SUGGESTED = [
  {
    label: "Cross-brand",
    title: "Compare CTAs across financing campaigns",
    body: "Find ads using deceptive_urgency across automotive and finance brands."
  },
  {
    label: "Duplicates",
    title: "Find near-duplicates of a known ad",
    body: "Use vector similarity to surface campaign variants of a single creative."
  },
  {
    label: "Roll-up",
    title: "Summarize this week's sensitive ads",
    body: "Aggregate ingested ads in regulated categories for the last 7 days."
  },
  {
    label: "Quality",
    title: "Show all sensitive ads with no offer",
    body: "Highlight regulated content lacking an extracted offer or CTA."
  }
];

export function MessageList({
  messages,
  tools,
  draft,
  streaming,
  onPrompt
}: {
  messages: AgentMessage[];
  tools: ToolCard[];
  draft?: string;
  streaming?: boolean;
  onPrompt: (text: string) => void;
}) {
  if (messages.length === 0 && !draft && tools.length === 0) {
    return (
      <div className="chat-empty">
        <div className="glyph" />
        <div>
          <h2>Ask ARGUS about your ads</h2>
          <p>
            The agent uses read-only tools to query the local SQLite database, run hybrid
            search, compare ads, and summarize evidence. Phase 9 wires it to live tool calls.
          </p>
        </div>
        <div className="suggested-grid">
          {SUGGESTED.map((s) => (
            <button
              key={s.title}
              className="suggest-card"
              onClick={() => onPrompt(s.title)}
            >
              <span className="label">{s.label}</span>
              <span style={{ color: "var(--fg)" }}>{s.title}</span>
              <span style={{ color: "var(--fg-mute)", fontSize: 11.5 }}>{s.body}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="chat-scroll">
      <div className="chat-message-list">
        {messages.map((message, index) => (
          <Bubble key={`${message.role}-${index}`} role={message.role} content={message.content ?? ""} />
        ))}
        {tools.map((tool) => (
          <ToolCallCard key={tool.id} tool={tool} />
        ))}
        {draft || streaming ? (
          <div className="bubble-assistant">
            <div className="avatar" />
            <div className="body">
              {draft}
              {streaming ? <span className="streaming-cursor" /> : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Bubble({ role, content }: { role: AgentMessage["role"]; content: string }) {
  if (role === "user") {
    return <div className="bubble-user">{content}</div>;
  }
  return (
    <div className="bubble-assistant">
      <div className="avatar" />
      <div className="body">{content}</div>
    </div>
  );
}
