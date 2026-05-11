import { useState } from "react";

import { SendIcon, StopIcon } from "../../lib/icons";

const ACTIVE_TOOLS = [
  "list_ads",
  "hybrid_search",
  "compare_ads",
  "aggregate",
  "vector_similarity"
];

export function ChatInput({
  disabled,
  streaming,
  onSubmit,
  onStop
}: {
  disabled?: boolean;
  streaming?: boolean;
  onSubmit: (message: string) => void;
  onStop: () => void;
}) {
  const [value, setValue] = useState("");

  return (
    <div className="chat-input-wrap">
      <div className="chat-input-inner">
        <div className="chat-input-meta">
          <span>ARGUS · tool-calling agent</span>
          <span className="tools-active">
            {ACTIVE_TOOLS.map((tool) => (
              <span key={tool} className="tool-chip">
                {tool}
              </span>
            ))}
          </span>
        </div>
        <div className="chat-textarea-wrap">
          <textarea
            className="chat-textarea"
            placeholder="Ask about your ads…"
            value={value}
            disabled={disabled}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (value.trim()) {
                  onSubmit(value.trim());
                  setValue("");
                }
              }
            }}
            rows={1}
          />
          <div className="chat-input-row">
            <div className="left">
              <button className="btn btn-sm" disabled>
                Context: all ads
              </button>
              <button className="btn btn-sm" disabled>
                SQL mode off
              </button>
            </div>
            {streaming ? (
              <button className="btn btn-sm btn-icon" onClick={onStop} title="Stop streaming">
                <StopIcon size={11} />
              </button>
            ) : (
              <button
                className="btn btn-sm btn-primary"
                disabled={disabled || !value.trim()}
                onClick={() => {
                  if (value.trim()) {
                    onSubmit(value.trim());
                    setValue("");
                  }
                }}
              >
                <SendIcon size={11} />
                <span>Send</span>
                <span className="kbd" style={{ marginLeft: 4 }}>
                  ⏎
                </span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
