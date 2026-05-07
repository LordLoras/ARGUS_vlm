import { useState } from "react";

import { CloseIcon, SparkleIcon } from "../../lib/icons";

export type DiscoverProposal = {
  id: string;
  name: string;
  brand?: string | null;
  count?: number;
  mean_similarity?: number | null;
};

export function DiscoverDialog({
  open,
  proposals,
  onClose,
  onAccept
}: {
  open: boolean;
  proposals: DiscoverProposal[];
  onClose: () => void;
  onAccept: (selectedIds: string[]) => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  return (
    <div className={`modal-overlay ${open ? "open" : ""}`} onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span style={{ color: "var(--accent-2)" }}>
            <SparkleIcon size={14} />
          </span>
          <h3>Discovered campaign candidates</h3>
          <button
            className="btn btn-icon btn-ghost"
            style={{ marginLeft: "auto" }}
            onClick={onClose}
          >
            <CloseIcon size={12} />
          </button>
        </div>
        <div className="modal-body">
          {proposals.length === 0 ? (
            <div className="obs-empty" style={{ padding: 24, textAlign: "center" }}>
              No candidate clusters yet. Try again after more ads are embedded.
            </div>
          ) : (
            proposals.map((p) => (
              <div
                key={p.id}
                className="proposal"
                onClick={() => toggle(p.id)}
              >
                <span className={`check ${selected.has(p.id) ? "on" : ""}`} />
                <div>
                  <div className="pname">{p.name}</div>
                  <div className="pmeta">
                    {p.brand ?? "no brand"} · {p.id}
                  </div>
                </div>
                <span className="pcount">{p.count ?? 0} ads</span>
                <span className="pscore">
                  {p.mean_similarity != null ? p.mean_similarity.toFixed(2) : "—"}
                </span>
              </div>
            ))
          )}
        </div>
        <div className="modal-foot">
          <span style={{ color: "var(--fg-mute)", fontSize: 12 }}>
            {selected.size} selected
          </span>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            <button className="btn" onClick={onClose}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              disabled={selected.size === 0}
              onClick={() => onAccept(Array.from(selected))}
            >
              Accept selected
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
