import { FormEvent, useEffect, useState } from "react";

import { CloseIcon, PlusIcon } from "../../lib/icons";

export type CreateCampaignInput = {
  name: string;
  advertiser?: string | null;
  brand?: string | null;
  theme?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  description?: string | null;
};

export function CreateCampaignDialog({
  open,
  onClose,
  onCreate,
  saving,
  initial,
  title = "New campaign",
  submitLabel = "Create"
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (input: CreateCampaignInput) => void;
  saving?: boolean;
  initial?: Partial<CreateCampaignInput>;
  title?: string;
  submitLabel?: string;
}) {
  const [name, setName] = useState("");
  const [advertiser, setAdvertiser] = useState("");
  const [brand, setBrand] = useState("");
  const [theme, setTheme] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setAdvertiser(initial?.advertiser ?? "");
    setBrand(initial?.brand ?? "");
    setTheme(initial?.theme ?? "");
    setStartDate(initial?.start_date ?? "");
    setEndDate(initial?.end_date ?? "");
    setDescription(initial?.description ?? "");
  }, [initial, open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;
    onCreate({
      name: trimmedName,
      advertiser: advertiser.trim() || null,
      brand: brand.trim() || null,
      theme: theme.trim() || null,
      start_date: startDate || null,
      end_date: endDate || null,
      description: description.trim() || null
    });
  };

  return (
    <div className={`modal-overlay ${open ? "open" : ""}`} onClick={onClose}>
      <form className="modal modal-sm" onSubmit={submit} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <span style={{ color: "var(--accent-2)" }}>
            <PlusIcon size={14} />
          </span>
          <h3>{title}</h3>
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
            <span>Name</span>
            <input
              className="input"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
            />
          </label>
          <label>
            <span>Brand</span>
            <input
              className="input"
              value={brand}
              onChange={(event) => setBrand(event.target.value)}
            />
          </label>
          <label>
            <span>Advertiser</span>
            <input
              className="input"
              value={advertiser}
              onChange={(event) => setAdvertiser(event.target.value)}
            />
          </label>
          <label>
            <span>Theme</span>
            <input
              className="input"
              value={theme}
              onChange={(event) => setTheme(event.target.value)}
            />
          </label>
          <div className="form-two">
            <label>
              <span>Start date</span>
              <input
                className="input"
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
              />
            </label>
            <label>
              <span>End date</span>
              <input
                className="input"
                type="date"
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
              />
            </label>
          </div>
          <label>
            <span>Description</span>
            <textarea
              className="input"
              rows={3}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
        </div>
        <div className="modal-foot">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" disabled={!name.trim() || saving} type="submit">
            {submitLabel}
          </button>
        </div>
      </form>
    </div>
  );
}
