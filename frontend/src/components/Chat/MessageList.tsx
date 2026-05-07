import { ToolCallCard, type ToolCard } from "./ToolCallCard";

type RenderedMessage = { role: "user" | "assistant"; content: string };

const SUGGESTED = [
  {
    label: "Roll-up",
    title: "How many ads do we have per brand?",
    body: "Use the aggregate tool grouped by brand_name."
  },
  {
    label: "Cross-brand",
    title: "Find ads with deceptive_urgency in automotive",
    body: "Use hybrid_search with the keyword and brand filter."
  },
  {
    label: "Duplicates",
    title: "Show ads similar to ad_xxxxxxxx",
    body: "Use vector_similarity on a seed ad id."
  },
  {
    label: "Compare",
    title: "Compare two ads and explain the difference",
    body: "Use compare_ads with two ad ids; the agent summarizes the verdict."
  }
];

export function MessageList({
  messages,
  tools,
  streaming,
  onPrompt
}: {
  messages: RenderedMessage[];
  tools: ToolCard[];
  streaming?: boolean;
  onPrompt: (text: string) => void;
}) {
  if (messages.length === 0 && tools.length === 0) {
    return (
      <div className="chat-empty">
        <div className="glyph" />
        <div>
          <h2>Ask ARGUS about your ads</h2>
          <p>
            The agent uses read-only tools to query the local SQLite database, run hybrid
            search, compare ads, and summarize evidence.
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
          <Bubble
            key={`${message.role}-${index}`}
            role={message.role}
            content={message.content}
          />
        ))}
        {tools.map((tool) => (
          <ToolCallCard key={tool.id} tool={tool} />
        ))}
        {streaming ? (
          <div className="bubble-assistant">
            <div className="avatar" />
            <div className="body">
              <span className="streaming-cursor" />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Bubble({ role, content }: RenderedMessage) {
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
