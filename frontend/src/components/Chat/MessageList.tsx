import { TerminalSquare } from "lucide-react";

import type { AgentMessage } from "../../lib/types";
import { EmptyState } from "../shared/EmptyState";
import { ToolCallCard, type ToolCard } from "./ToolCallCard";

const prompts = [
  "How many ads in the database?",
  "Show me ads with similar messaging across different brands",
  "Find duplicates of ad_a3b9k2x7",
  "Which campaign is the largest?",
  "Summarize all health_wellness ads",
  "Which ads use deceptive_urgency tactics?"
];

export function MessageList({
  messages,
  tools,
  draft,
  onPrompt
}: {
  messages: AgentMessage[];
  tools: ToolCard[];
  draft?: string;
  onPrompt: (text: string) => void;
}) {
  if (messages.length === 0 && !draft && tools.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="w-full max-w-3xl">
          <EmptyState
            icon={<TerminalSquare className="h-10 w-10" />}
            title="Ask about your ads"
            body="The agent will use read-only tools to query ads, find similar clips, and aggregate metrics once Phase 9 endpoints are available."
          />
          <div className="mt-5 grid grid-cols-3 gap-3">
            {prompts.map((prompt) => (
              <button key={prompt} onClick={() => onPrompt(prompt)} className="rounded-lg border border-border bg-surface p-3 text-left font-mono text-sm transition hover:border-violet-400 hover:bg-muted">
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-5">
      {messages.map((message, index) => (
        <Bubble key={`${message.role}-${index}`} role={message.role} content={message.content ?? ""} />
      ))}
      {tools.map((tool) => (
        <ToolCallCard key={tool.id} tool={tool} />
      ))}
      {draft && <Bubble role="assistant" content={draft} />}
    </div>
  );
}

function Bubble({ role, content }: { role: AgentMessage["role"]; content: string }) {
  const user = role === "user";
  return (
    <div className={`flex ${user ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-2xl rounded-lg px-4 py-3 text-sm ${user ? "bg-violet-500/25 text-violet-50" : "bg-muted text-foreground"}`}>
        {content}
      </div>
    </div>
  );
}
