import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "../../lib/utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  className,
  variant = "secondary",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; children: ReactNode }) {
  return (
    <button
      className={cn(
        "inline-flex h-9 items-center justify-center gap-2 rounded-md px-3 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-accent text-accent-foreground hover:bg-violet-500",
        variant === "secondary" && "border border-border bg-muted text-foreground hover:bg-slate-800",
        variant === "ghost" && "text-muted-foreground hover:bg-muted hover:text-foreground",
        variant === "danger" && "border border-red-900/60 bg-red-950/40 text-red-200 hover:bg-red-900/50",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
