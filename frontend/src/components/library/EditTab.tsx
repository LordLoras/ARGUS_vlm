import { useEffect, useState } from "react";

import { categories } from "../../lib/taxonomy";
import type { AdDetail } from "../../lib/types";
import { CloseIcon, PlusIcon } from "../../lib/icons";

export type EditPatch = {
  brand_name?: string | null;
  advertiser_name?: string | null;
  products_text?: string | null;
  primary_category?: string | null;
  subcategory?: string | null;
  tagline?: string | null;
  offers?: Array<{ text: string }>;
  ctas?: Array<{ text: string }>;
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
  const ent = detail.marketing_entities;

  const [brand, setBrand] = useState(detail.ad.brand_name ?? "");
  const [advertiser, setAdvertiser] = useState(detail.ad.advertiser_name ?? "");
  const [products, setProducts] = useState(detail.ad.products_text ?? "");
  const [category, setCategory] = useState(
    detail.ad.primary_category ?? detail.classification?.primary_category ?? "other"
  );
  const [subcategory, setSubcategory] = useState(detail.ad.subcategory ?? ent?.subcategory ?? "");
  const [tagline, setTagline] = useState(ent?.brand?.tagline ?? "");
  const [offers, setOffers] = useState<string[]>(
    (ent?.offers ?? []).map((o) => o.text ?? o.value ?? "").filter(Boolean)
  );
  const [ctas, setCtas] = useState<string[]>(
    (ent?.ctas ?? []).map((c) => c.text ?? "").filter(Boolean)
  );
  const [newOffer, setNewOffer] = useState("");
  const [newCta, setNewCta] = useState("");

  useEffect(() => {
    setBrand(detail.ad.brand_name ?? "");
    setAdvertiser(detail.ad.advertiser_name ?? "");
    setProducts(detail.ad.products_text ?? "");
    setCategory(detail.ad.primary_category ?? detail.classification?.primary_category ?? "other");
    setSubcategory(detail.ad.subcategory ?? ent?.subcategory ?? "");
    setTagline(ent?.brand?.tagline ?? "");
    setOffers((ent?.offers ?? []).map((o) => o.text ?? o.value ?? "").filter(Boolean));
    setCtas((ent?.ctas ?? []).map((c) => c.text ?? "").filter(Boolean));
    setNewOffer("");
    setNewCta("");
  }, [
    detail.ad.id,
    detail.ad.brand_name,
    detail.ad.advertiser_name,
    detail.ad.products_text,
    detail.ad.primary_category,
    detail.ad.subcategory,
    detail.marketing_entities
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
        <Field label="Advertiser">
          <input
            className="input"
            value={advertiser}
            onChange={(e) => setAdvertiser(e.target.value)}
            placeholder="advertiser (dealer, store, business)"
          />
        </Field>
        <Field label="Tagline">
          <input
            className="input"
            value={tagline}
            onChange={(e) => setTagline(e.target.value)}
            placeholder="tagline"
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
        <Field label="Subcategory">
          <input
            className="input"
            value={subcategory}
            onChange={(e) => setSubcategory(e.target.value)}
            placeholder="e.g. SUV, fast casual, energy drink"
          />
        </Field>

        <Field label={`Offers (${offers.length})`}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {offers.map((text, idx) => (
              <div key={idx} style={{ display: "flex", gap: 4, alignItems: "center" }}>
                <input
                  className="input"
                  style={{ flex: 1 }}
                  value={text}
                  onChange={(e) => {
                    const next = [...offers];
                    next[idx] = e.target.value;
                    setOffers(next);
                  }}
                />
                <button
                  className="btn btn-sm btn-icon"
                  onClick={() => setOffers(offers.filter((_, i) => i !== idx))}
                  title="Remove"
                >
                  <CloseIcon size={10} />
                </button>
              </div>
            ))}
            <div style={{ display: "flex", gap: 4 }}>
              <input
                className="input"
                style={{ flex: 1 }}
                value={newOffer}
                onChange={(e) => setNewOffer(e.target.value)}
                placeholder="Add offer…"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newOffer.trim()) {
                    setOffers([...offers, newOffer.trim()]);
                    setNewOffer("");
                  }
                }}
              />
              <button
                className="btn btn-sm"
                onClick={() => {
                  if (newOffer.trim()) {
                    setOffers([...offers, newOffer.trim()]);
                    setNewOffer("");
                  }
                }}
              >
                <PlusIcon size={10} />
              </button>
            </div>
          </div>
        </Field>

        <Field label={`CTAs (${ctas.length})`}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {ctas.map((text, idx) => (
              <div key={idx} style={{ display: "flex", gap: 4, alignItems: "center" }}>
                <input
                  className="input"
                  style={{ flex: 1 }}
                  value={text}
                  onChange={(e) => {
                    const next = [...ctas];
                    next[idx] = e.target.value;
                    setCtas(next);
                  }}
                />
                <button
                  className="btn btn-sm btn-icon"
                  onClick={() => setCtas(ctas.filter((_, i) => i !== idx))}
                  title="Remove"
                >
                  <CloseIcon size={10} />
                </button>
              </div>
            ))}
            <div style={{ display: "flex", gap: 4 }}>
              <input
                className="input"
                style={{ flex: 1 }}
                value={newCta}
                onChange={(e) => setNewCta(e.target.value)}
                placeholder="Add CTA…"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && newCta.trim()) {
                    setCtas([...ctas, newCta.trim()]);
                    setNewCta("");
                  }
                }}
              />
              <button
                className="btn btn-sm"
                onClick={() => {
                  if (newCta.trim()) {
                    setCtas([...ctas, newCta.trim()]);
                    setNewCta("");
                  }
                }}
              >
                <PlusIcon size={10} />
              </button>
            </div>
          </div>
        </Field>

        <div className="row" style={{ justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
          <button
            className="btn btn-primary"
            disabled={saving}
            onClick={() =>
              onSave({
                brand_name: brand || null,
                advertiser_name: advertiser || null,
                products_text: products || null,
                primary_category: category,
                subcategory: subcategory || null,
                tagline: tagline || null,
                offers: offers.filter(Boolean).map((text) => ({ text })),
                ctas: ctas.filter(Boolean).map((text) => ({ text })),
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
