import { ChevronRight } from "lucide-react";
import { useState } from "react";

export type ToolCard = {
  id: string;
  name: string;
  args: unknown;
  result?: unknown;
  summary?: string;
  truncated?: boolean;
};

export function ToolCallCard({ tool }: { tool: ToolCard }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="ml-8 rounded-md border border-border border-l-violet-400 bg-surface">
      <button className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm" onClick={() => setOpen(!open)}>
        <ChevronRight className={`h-4 w-4 transition ${open ? "rotate-90" : ""}`} />
        <span className="font-mono text-violet-100">{tool.name}</span>
        <span className="text-muted-foreground">→ {tool.summary || "calling..."}</span>
        {tool.truncated && <span className="ml-auto rounded bg-amber-500/10 px-2 py-0.5 text-xs text-amber-200">truncated</span>}
      </button>
      {open && (
        <div className="space-y-2 border-t border-border p-3">
          <CodeBlock label="args" value={tool.args} />
          <CodeBlock label="result" value={tool.result ?? null} />
        </div>
      )}
    </div>
  );
}

function CodeBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <div className="mb-1 text-xs uppercase text-muted-foreground">{label}</div>
      <pre className="max-h-56 overflow-auto rounded-md bg-background p-3 text-xs text-slate-200">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
