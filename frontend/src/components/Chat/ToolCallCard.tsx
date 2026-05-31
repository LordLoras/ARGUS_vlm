import { useState } from "react";

import { ChevronRightIcon } from "../../lib/icons";

export type ToolCard = {
  id: string;
  name: string;
  args: unknown;
  result?: unknown;
  summary?: string;
  status?: "running" | "done" | "failed";
  durationMs?: number;
  truncated?: boolean;
};

export function ToolCallCard({ tool }: { tool: ToolCard }) {
  const [open, setOpen] = useState(false);
  const status = tool.status ?? (tool.result != null ? "done" : "running");
  return (
    <div className={`tool-call ${open ? "open" : ""}`}>
      <button
        type="button"
        className="tc-head"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="chev">
          <ChevronRightIcon size={11} />
        </span>
        <span style={{ display: "flex", gap: 6, alignItems: "center", minWidth: 0 }}>
          <span className="tool-name">{tool.name}</span>
          <span className="arrow">→</span>
          <span className="tool-summary">{tool.summary || (status === "running" ? "calling…" : "no result")}</span>
        </span>
        <span className="tc-time">{tool.durationMs != null ? `${tool.durationMs}ms` : ""}</span>
        <span className={`tc-status ${status}`}>{status}</span>
      </button>
      <div className="tc-body">
        <Section label="Arguments" value={tool.args} />
        <Section label="Result" value={tool.result ?? null} truncated={tool.truncated} />
      </div>
    </div>
  );
}

function Section({ label, value, truncated }: { label: string; value: unknown; truncated?: boolean }) {
  return (
    <div className="tc-section">
      <div className="tc-section-label">
        {label}
        {truncated ? (
          <span className="badge badge-amber" style={{ marginLeft: 6 }}>
            truncated
          </span>
        ) : null}
      </div>
      <pre dangerouslySetInnerHTML={{ __html: highlight(value) }} />
    </div>
  );
}

function highlight(value: unknown) {
  const text = JSON.stringify(value, null, 2) ?? "null";
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped
    .replace(
      /("(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
      (match) => {
        let cls = "json-num";
        if (/^"/.test(match)) {
          cls = /:$/.test(match) ? "json-key" : "json-str";
        } else if (/true|false/.test(match)) cls = "json-bool";
        else if (/null/.test(match)) cls = "json-null";
        return `<span class="${cls}">${match}</span>`;
      }
    )
    .replace(/[{}\[\],]/g, (m) => `<span class="json-punct">${m}</span>`);
}
