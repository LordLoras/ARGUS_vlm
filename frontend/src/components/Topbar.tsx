import type { ReactNode } from "react";

export function Topbar({ crumbs, actions }: { crumbs: string[]; actions?: ReactNode }) {
  return (
    <header className="topbar">
      <div className="crumbs">
        {crumbs.map((c, i) =>
          i === crumbs.length - 1 ? (
            <span key={`${c}-${i}`} className="here">
              {c}
            </span>
          ) : (
            <span key={`${c}-${i}`} className="row">
              <span>{c}</span>
              <span className="sep">/</span>
            </span>
          )
        )}
      </div>
      <div className="topbar-actions">
        {actions}
      </div>
    </header>
  );
}
