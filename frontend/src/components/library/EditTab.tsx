import { useEffect, useState } from "react";

import { categories } from "../../lib/taxonomy";
import type { AdDetail } from "../../lib/types";
import { CloseIcon, PlusIcon } from "../../lib/icons";
import { knowledgeApi, type IABEntry } from "../../lib/knowledge-api";

export type EditPatch = {
  brand_name?: string | null;
  advertiser_name?: string | null;
  promotion_name?: string | null;
  products_text?: string | null;
  primary_category?: string | null;
  subcategory?: string | null;
  iab_product_id?: string | null;
  iab_content_ids?: string[] | null;
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
  const [promotion, setPromotion] = useState(detail.ad.promotion_name ?? ent?.promotion_name ?? "");
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
  const [iabProductId, setIabProductId] = useState(
    detail.classification?.iab_category?.iab_unique_id ?? detail.ad.iab_unique_id ?? ""
  );
  const [iabProductLabel, setIabProductLabel] = useState(
    detail.classification?.iab_category?.full_path ?? detail.ad.iab_full_path ?? ""
  );
  const [iabProductQuery, setIabProductQuery] = useState("");
  const [iabProductResults, setIabProductResults] = useState<IABEntry[]>([]);
  const [iabContent, setIabContent] = useState<IABSelection[]>(currentContentSelections(detail));
  const [iabContentQuery, setIabContentQuery] = useState("");
  const [iabContentResults, setIabContentResults] = useState<IABEntry[]>([]);
  const [newOffer, setNewOffer] = useState("");
  const [newCta, setNewCta] = useState("");

  useEffect(() => {
    setBrand(detail.ad.brand_name ?? "");
    setAdvertiser(detail.ad.advertiser_name ?? "");
    setPromotion(detail.ad.promotion_name ?? ent?.promotion_name ?? "");
    setProducts(detail.ad.products_text ?? "");
    setCategory(detail.ad.primary_category ?? detail.classification?.primary_category ?? "other");
    setSubcategory(detail.ad.subcategory ?? ent?.subcategory ?? "");
    setTagline(ent?.brand?.tagline ?? "");
    setOffers((ent?.offers ?? []).map((o) => o.text ?? o.value ?? "").filter(Boolean));
    setCtas((ent?.ctas ?? []).map((c) => c.text ?? "").filter(Boolean));
    setIabProductId(detail.classification?.iab_category?.iab_unique_id ?? detail.ad.iab_unique_id ?? "");
    setIabProductLabel(detail.classification?.iab_category?.full_path ?? detail.ad.iab_full_path ?? "");
    setIabProductQuery("");
    setIabProductResults([]);
    setIabContent(currentContentSelections(detail));
    setIabContentQuery("");
    setIabContentResults([]);
    setNewOffer("");
    setNewCta("");
  }, [
    detail.ad.id,
    detail.ad.brand_name,
    detail.ad.advertiser_name,
    detail.ad.promotion_name,
    detail.ad.products_text,
    detail.ad.primary_category,
    detail.ad.subcategory,
    detail.ad.iab_unique_id,
    detail.ad.iab_full_path,
    detail.ad.iab_content_ids,
    detail.ad.iab_content_categories_json,
    detail.classification?.iab_category,
    detail.classification?.iab_content_categories,
    detail.marketing_entities
  ]);

  const searchProductIab = async () => {
    if (!iabProductQuery.trim()) return;
    setIabProductResults(await knowledgeApi.searchProduct(iabProductQuery.trim()));
  };

  const searchContentIab = async () => {
    if (!iabContentQuery.trim()) return;
    setIabContentResults(await knowledgeApi.searchContent(iabContentQuery.trim()));
  };

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
        <Field label="Promotion / event">
          <input
            className="input"
            value={promotion}
            onChange={(e) => setPromotion(e.target.value)}
            placeholder="e.g. America 250, Jeep Declaration of Deals"
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
        <Field label="IAB product">
          <div style={{ display: "grid", gap: 6 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                className="input"
                style={{ flex: 1 }}
                value={iabProductQuery}
                onChange={(e) => setIabProductQuery(e.target.value)}
                placeholder={iabProductLabel || "Search product taxonomy"}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void searchProductIab();
                }}
              />
              <button className="btn btn-sm" onClick={() => void searchProductIab()}>
                Search
              </button>
              <button
                className="btn btn-sm"
                onClick={() => {
                  setIabProductId("");
                  setIabProductLabel("");
                }}
              >
                Clear
              </button>
            </div>
            {iabProductId ? (
              <div className="badge badge-mono" style={{ width: "fit-content" }}>
                {iabProductId} · {iabProductLabel || "selected"}
              </div>
            ) : null}
            {iabProductResults.length ? (
              <div style={{ display: "grid", gap: 4 }}>
                {iabProductResults.slice(0, 8).map((entry) => (
                  <TaxonomyPickRow
                    key={entry.unique_id}
                    entry={entry}
                    onPick={() => {
                      setIabProductId(entry.unique_id);
                      setIabProductLabel(entry.full_path ?? entry.name);
                      setIabProductResults([]);
                      setIabProductQuery("");
                    }}
                  />
                ))}
              </div>
            ) : null}
          </div>
        </Field>
        <Field label={`Secondary IAB (${iabContent.length})`}>
          <div style={{ display: "grid", gap: 6 }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {iabContent.map((entry) => (
                <button
                  key={entry.id}
                  className="btn btn-sm"
                  onClick={() => setIabContent(iabContent.filter((item) => item.id !== entry.id))}
                  title="Remove content category"
                >
                  <span className="mono">{entry.id}</span>
                  <span>{entry.label}</span>
                  <CloseIcon size={10} />
                </button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <input
                className="input"
                style={{ flex: 1 }}
                value={iabContentQuery}
                onChange={(e) => setIabContentQuery(e.target.value)}
                placeholder="Search content taxonomy"
                onKeyDown={(e) => {
                  if (e.key === "Enter") void searchContentIab();
                }}
              />
              <button className="btn btn-sm" onClick={() => void searchContentIab()}>
                Search
              </button>
              <button className="btn btn-sm" onClick={() => setIabContent([])}>
                Clear
              </button>
            </div>
            {iabContentResults.length ? (
              <div style={{ display: "grid", gap: 4 }}>
                {iabContentResults.slice(0, 8).map((entry) => (
                  <TaxonomyPickRow
                    key={entry.unique_id}
                    entry={entry}
                    onPick={() => {
                      if (!iabContent.some((item) => item.id === entry.unique_id)) {
                        setIabContent([
                          ...iabContent,
                          { id: entry.unique_id, label: entry.full_path ?? entry.name }
                        ]);
                      }
                      setIabContentResults([]);
                      setIabContentQuery("");
                    }}
                  />
                ))}
              </div>
            ) : null}
          </div>
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
                promotion_name: promotion || null,
                products_text: products || null,
                primary_category: category,
                subcategory: subcategory || null,
                iab_product_id: iabProductId || null,
                iab_content_ids: iabContent.map((entry) => entry.id),
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

type IABSelection = { id: string; label: string };

function TaxonomyPickRow({ entry, onPick }: { entry: IABEntry; onPick: () => void }) {
  return (
    <button
      className="btn"
      style={{
        justifyContent: "flex-start",
        height: "auto",
        padding: "6px 8px",
        textAlign: "left"
      }}
      onClick={onPick}
    >
      <span className="mono" style={{ minWidth: 44 }}>
        {entry.unique_id}
      </span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
        {entry.full_path ?? entry.name}
      </span>
    </button>
  );
}

function currentContentSelections(detail: AdDetail): IABSelection[] {
  const categories = detail.classification?.iab_content_categories ?? [];
  if (categories.length) {
    return categories.map((category) => ({
      id: category.iab_unique_id,
      label: category.full_path
    }));
  }
  if (detail.ad.iab_content_categories_json) {
    try {
      const parsed = JSON.parse(detail.ad.iab_content_categories_json);
      if (Array.isArray(parsed)) {
        return parsed
          .filter((item) => item && typeof item === "object" && "iab_unique_id" in item)
          .map((item) => ({
            id: String(item.iab_unique_id),
            label: String(item.full_path ?? item.selected_category ?? item.iab_unique_id)
          }));
      }
    } catch {
      // Ignore malformed cached projection JSON.
    }
  }
  return (detail.ad.iab_content_ids ?? "")
    .split(",")
    .map((id) => id.trim())
    .filter(Boolean)
    .map((id) => ({ id, label: id }));
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
