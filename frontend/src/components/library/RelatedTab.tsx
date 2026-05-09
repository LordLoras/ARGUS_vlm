import { useMemo, useState } from "react";

import { ChevronRightIcon } from "../../lib/icons";
import type { FieldDifference, RelatedAd, RelatedAds } from "../../lib/types";

type RelatedSection = "brand" | "peers";

export function RelatedTab({
  related,
  onSelectAd
}: {
  related?: RelatedAds;
  onSelectAd?: (adId: string) => void;
}) {
  const items = related?.semantically_similar ?? [];
  const grouped = useMemo(() => groupRelated(items), [items]);
  const [section, setSection] = useState<RelatedSection>("brand");
  const visibleItems = section === "brand" ? grouped.brand : grouped.peers;

  if (items.length === 0 && !related?.exact_duplicate_of && !related?.near_duplicate_of) {
    return <div className="obs-empty">No related ads indexed yet.</div>;
  }

  return (
    <>
      {related?.exact_duplicate_of ? (
        <DuplicateCard title="Exact duplicate" adId={related.exact_duplicate_of} onSelectAd={onSelectAd} />
      ) : null}
      {related?.near_duplicate_of ? (
        <DuplicateCard title="Near duplicate" adId={related.near_duplicate_of} onSelectAd={onSelectAd} />
      ) : null}

      <div className="related-switch" role="tablist" aria-label="Related ads sections">
        <button
          className={section === "brand" ? "active" : ""}
          onClick={() => setSection("brand")}
          type="button"
        >
          <span>Brand / campaigns</span>
          <span className="count-pill">{grouped.brand.length}</span>
        </button>
        <button
          className={section === "peers" ? "active" : ""}
          onClick={() => setSection("peers")}
          type="button"
        >
          <span>Category peers</span>
          <span className="count-pill">{grouped.peers.length}</span>
        </button>
      </div>

      <div className="dcard">
        <div className="dcard-head">
          <span>{section === "brand" ? "Same brand and campaign variants" : "Broad category matches"}</span>
          <span className="count-pill">{visibleItems.length}</span>
        </div>
        <div className="dcard-body related-list">
          {visibleItems.length === 0 ? (
            <div className="obs-empty">
              {section === "brand"
                ? "No same-brand campaign variants found."
                : "No different-brand category peers found."}
            </div>
          ) : (
            visibleItems.map((item) => (
              <RelatedCard key={item.ad_id} item={item} onSelectAd={onSelectAd} />
            ))
          )}
        </div>
      </div>
    </>
  );
}

function DuplicateCard({
  title,
  adId,
  onSelectAd
}: {
  title: string;
  adId: string;
  onSelectAd?: (adId: string) => void;
}) {
  return (
    <div className="dcard">
      <div className="dcard-head">
        <span>{title}</span>
      </div>
      <div className="dcard-body related-duplicate">
        <button className="related-id" onClick={() => onSelectAd?.(adId)} type="button">
          {adId}
        </button>
      </div>
    </div>
  );
}

function RelatedCard({
  item,
  onSelectAd
}: {
  item: RelatedAd;
  onSelectAd?: (adId: string) => void;
}) {
  const differences = preferredDifferences(item.differences ?? []);

  return (
    <article className="related-card">
      <div className="related-card-head">
        <div>
          <button className="related-id" onClick={() => onSelectAd?.(item.ad_id)} type="button">
            {item.ad_id}
          </button>
          <div className="related-verdict">{verdictLabel(item.verdict)}</div>
        </div>
        {item.verdict ? <span className={`badge ${badgeClass(item.verdict)}`}>{verdictLabel(item.verdict)}</span> : null}
        <button className="btn btn-sm" onClick={() => onSelectAd?.(item.ad_id)} type="button">
          <span>Open</span>
          <ChevronRightIcon size={10} />
        </button>
      </div>

      <div className="related-score-grid">
        <ScoreRow label="overall" value={item.overall_score} tone="overall" />
        <ScoreRow label="visual" value={item.visual_score} tone="visual" />
        <ScoreRow label="text" value={item.text_score} tone="text" />
      </div>

      {differences.length > 0 ? (
        <div className="related-diff-list">
          {differences.map((diff) => (
            <div className="related-diff" key={diff.field}>
              <div className="related-diff-field">{fieldLabel(diff.field)}</div>
              <div className="related-diff-values">
                <span>{formatDiffValue(diff.left)}</span>
                <span>{formatDiffValue(diff.right)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function groupRelated(items: RelatedAd[]) {
  return items.reduce(
    (acc, item) => {
      if (isCategoryPeer(item)) acc.peers.push(item);
      else acc.brand.push(item);
      return acc;
    },
    { brand: [] as RelatedAd[], peers: [] as RelatedAd[] }
  );
}

function isCategoryPeer(item: RelatedAd) {
  if (item.verdict === "similar_messaging_different_brand") return true;
  const diffs = item.differences ?? [];
  const hasBrandDiff = diffs.some((diff) => diff.field === "brand");
  const hasSubcategoryMatch = !diffs.some((diff) => diff.field === "subcategory");
  return hasBrandDiff && hasSubcategoryMatch;
}

function preferredDifferences(differences: FieldDifference[]) {
  const order = ["brand", "subcategory", "products", "prices", "offers", "primary_category"];
  return [...differences]
    .sort((a, b) => order.indexOf(a.field) - order.indexOf(b.field))
    .slice(0, 4);
}

function verdictLabel(verdict?: string | null) {
  switch (verdict) {
    case "near_duplicate":
      return "Near duplicate";
    case "same_campaign_different_sku":
      return "Different vehicle / SKU";
    case "same_campaign_different_offer":
      return "Different offer";
    case "similar_messaging_different_brand":
      return "Category peer";
    case "related":
      return "Related creative";
    default:
      return "Related";
  }
}

function badgeClass(verdict: string) {
  if (verdict === "similar_messaging_different_brand") return "badge-sky";
  if (verdict === "near_duplicate") return "badge-emerald";
  return "badge-violet";
}

function fieldLabel(field: string) {
  switch (field) {
    case "primary_category":
      return "Category";
    case "subcategory":
      return "Subcategory";
    default:
      return field.replace(/_/g, " ");
  }
}

function formatDiffValue(value?: string | string[] | null) {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  return value || "—";
}

function ScoreRow({
  label,
  value,
  tone
}: {
  label: string;
  value?: number | null;
  tone?: "overall" | "visual" | "text";
}) {
  const pct = value ? Math.max(0, Math.min(1, value)) : 0;
  return (
    <div className="score-row">
      <span className="lbl">{label}</span>
      <div className={`score-bar ${tone ?? ""}`}>
        <span style={{ width: `${pct * 100}%` }} />
      </div>
      <span className="num">{value != null ? value.toFixed(2) : "—"}</span>
    </div>
  );
}
