import { useEffect, useState } from "react";

import { categories } from "../../lib/taxonomy";
import type { AdDetail } from "../../lib/types";

export type EditPatch = {
  brand_name?: string | null;
  products_text?: string | null;
  primary_category?: string | null;
};

export function EditTab({
  detail,
  onSave,
  saving
}: {
  detail: AdDetail;
  onSave: (patch: EditPatch) => void;
  saving?: boolean;
}) {
  const [brand, setBrand] = useState(detail.ad.brand_name ?? "");
  const [products, setProducts] = useState(detail.ad.products_text ?? "");
  const [category, setCategory] = useState(
    detail.ad.primary_category ?? detail.classification?.primary_category ?? "other"
  );

  useEffect(() => {
    setBrand(detail.ad.brand_name ?? "");
    setProducts(detail.ad.products_text ?? "");
    setCategory(detail.ad.primary_category ?? detail.classification?.primary_category ?? "other");
  }, [
    detail.ad.id,
    detail.ad.brand_name,
    detail.ad.products_text,
    detail.ad.primary_category,
    detail.classification?.primary_category
  ]);

  return (
    <div className="dcard">
      <div className="dcard-head">
        <span>Edit curated fields</span>
      </div>
      <div className="dcard-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <Field label="Brand">
          <input
            className="input"
            value={brand}
            onChange={(e) => setBrand(e.target.value)}
            placeholder="brand"
          />
        </Field>
        <Field label="Products">
          <input
            className="input"
            value={products}
            onChange={(e) => setProducts(e.target.value)}
            placeholder="comma-separated"
          />
        </Field>
        <Field label="Category">
          <select
            className="input"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </Field>
        <div className="row" style={{ justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
          <button
            className="btn btn-primary"
            disabled={saving}
            onClick={() =>
              onSave({
                brand_name: brand || null,
                products_text: products || null,
                primary_category: category
              })
            }
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <span
        className="section-title"
        style={{ marginBottom: 0, fontSize: 10, color: "var(--fg-mute)" }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}
