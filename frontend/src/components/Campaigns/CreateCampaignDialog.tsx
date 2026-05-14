import { FormEvent, useEffect, useState } from "react";

import { CloseIcon, PlusIcon } from "../../lib/icons";

export type CreateCampaignInput = {
  name: string;
  brand?: string | null;
  theme?: string | null;
  description?: string | null;
};

export function CreateCampaignDialog({
  open,
  onClose,
  onCreate,
  saving
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (input: CreateCampaignInput) => void;
  saving?: boolean;
}) {
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [theme, setTheme] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (!open) return;
    setName("");
    setBrand("");
    setTheme("");
    setDescription("");
  }, [open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;
    onCreate({
      name: trimmedName,
      brand: brand.trim() || null,
      theme: theme.trim() || null,
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
          <h3>New campaign</h3>
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
            <span>Theme</span>
            <input
              className="input"
              value={theme}
              onChange={(event) => setTheme(event.target.value)}
            />
          </label>
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
            Create
          </button>
        </div>
      </form>
    </div>
  );
}
