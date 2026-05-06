import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "../../lib/utils";

export function Card({ className, children, ...props }: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) {
  return (
    <section
      className={cn("rounded-lg border border-border bg-surface/85 p-4 shadow-panel backdrop-blur", className)}
      {...props}
    >
      {children}
    </section>
  );
}

export function CardHeader({ className, children }: HTMLAttributes<HTMLDivElement> & { children: ReactNode }) {
  return <div className={cn("mb-3 flex items-center justify-between gap-3", className)}>{children}</div>;
}

export function CardTitle({ className, children }: HTMLAttributes<HTMLHeadingElement> & { children: ReactNode }) {
  return <h2 className={cn("text-sm font-semibold uppercase text-muted-foreground", className)}>{children}</h2>;
}
