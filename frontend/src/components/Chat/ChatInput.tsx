import { Send, Square } from "lucide-react";
import { useState } from "react";

import { Button } from "../ui/Button";
import { Textarea } from "../ui/Form";

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
    <div className="border-t border-border bg-background/95 p-4">
      <div className="mb-2 text-right font-mono text-xs text-muted-foreground">Tool calls and results are logged. Read-only DB access.</div>
      <div className="flex gap-3">
        <Textarea
          value={value}
          disabled={disabled || streaming}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (value.trim()) {
                onSubmit(value.trim());
                setValue("");
              }
            }
          }}
          placeholder="Ask about your ads..."
          className="max-h-36 min-h-12 flex-1"
        />
        <Button
          variant="primary"
          className="h-12 w-12 rounded-full p-0"
          disabled={disabled || (!streaming && !value.trim())}
          onClick={() => {
            if (streaming) {
              onStop();
            } else if (value.trim()) {
              onSubmit(value.trim());
              setValue("");
            }
          }}
        >
          {streaming ? <Square className="h-4 w-4" /> : <Send className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}
