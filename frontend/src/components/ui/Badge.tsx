import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "../../lib/utils";

export function Badge({
  className,
  children,
  tone = "neutral"
}: HTMLAttributes<HTMLSpanElement> & { children: ReactNode; tone?: "neutral" | "accent" | "amber" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium",
        tone === "neutral" && "border-border bg-muted text-muted-foreground",
        tone === "accent" && "border-violet-500/40 bg-violet-500/10 text-violet-200",
        tone === "amber" && "border-amber-400/30 bg-amber-500/10 text-amber-200",
        className
      )}
    >
      {children}
    </span>
  );
}
