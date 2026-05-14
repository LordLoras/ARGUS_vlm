import { useEffect, useState } from "react";

import type { Campaign } from "../../lib/types";
import { CloseIcon, PlusIcon } from "../../lib/icons";

export function CampaignAssignDialog({
  open,
  campaigns,
  adId,
  onClose,
  onAssign,
  assigning
}: {
  open: boolean;
  campaigns: Campaign[];
  adId: string;
  onClose: () => void;
  onAssign: (campaignId: string) => void;
  assigning?: boolean;
}) {
  const [selectedId, setSelectedId] = useState("");

  useEffect(() => {
    if (!open) return;
    setSelectedId(campaigns[0]?.id ?? "");
  }, [campaigns, open]);

  return (
    <div className={`modal-overlay ${open ? "open" : ""}`} onClick={onClose}>
      <div className="modal modal-sm" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span style={{ color: "var(--accent-2)" }}>
            <PlusIcon size={14} />
          </span>
          <h3>Add to campaign</h3>
          <button
            type="button"
            className="btn btn-icon btn-ghost"
            style={{ marginLeft: "auto" }}
            onClick={onClose}
          >
            <CloseIcon size={12} />
          </button>
        </div>
        <div className="modal-body form-grid">
          <label>
            <span>Ad</span>
            <input className="input mono" value={adId} readOnly />
          </label>
          <label>
            <span>Campaign</span>
            <select
              className="input"
              value={selectedId}
              onChange={(event) => setSelectedId(event.target.value)}
              disabled={campaigns.length === 0}
            >
              {campaigns.map((campaign) => (
                <option key={campaign.id} value={campaign.id}>
                  {campaign.name} ({campaign.id})
                </option>
              ))}
            </select>
          </label>
          {campaigns.length === 0 ? (
            <div className="obs-empty" style={{ padding: 18 }}>
              Create a campaign first from the Campaigns page.
            </div>
          ) : null}
        </div>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            disabled={!selectedId || assigning}
            onClick={() => onAssign(selectedId)}
            type="button"
          >
            Assign
          </button>
        </div>
      </div>
    </div>
  );
}
