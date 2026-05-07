import type { ReactNode } from "react";

export function EmptyState({
  icon,
  title,
  hint
}: {
  icon?: ReactNode;
  title: string;
  hint?: string;
}) {
  return (
    <div className="empty-block">
      {icon ? <div className="icon-wrap">{icon}</div> : null}
      <div>{title}</div>
      {hint ? <div className="hint">{hint}</div> : null}
    </div>
  );
}
