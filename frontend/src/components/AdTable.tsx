import { ChevronRightIcon } from "../lib/icons";
import { formatDuration, relativeTime } from "../lib/format";
import { aspectFromDims, deriveSeed } from "../lib/style-helpers";
import type { AdDetail, AdRecord } from "../lib/types";
import { CategoryBadge } from "./shared/CategoryBadge";
import { FrameThumbnail } from "./shared/FrameThumbnail";

const MAX_PRODUCTS = 3;

function formatSubLine(ad: AdRecord): string {
  const parts: string[] = [];
  if (ad.brand_name) parts.push(ad.brand_name);
  if (ad.promotion_name) parts.push(ad.promotion_name);
  if (ad.products_text) {
    const all = ad.products_text.split(/,\s*/).filter(Boolean);
    if (all.length > MAX_PRODUCTS) {
      parts.push(`${all.slice(0, MAX_PRODUCTS).join(", ")} +${all.length - MAX_PRODUCTS} more`);
    } else {
      parts.push(all.join(", "));
    }
  }
  return parts.join(" / ") || ad.id;
}

export function AdTable({
  ads,
  details,
  framePreviews,
  selectedId,
  onSelect
}: {
  ads: AdRecord[];
  details: Record<string, AdDetail | undefined>;
  framePreviews?: Record<string, string | undefined>;
  selectedId?: string | null;
  onSelect: (adId: string) => void;
}) {
  return (
    <div className="table-wrap">
      <table className="tbl">
        <thead>
          <tr>
            <th style={{ width: 120 }}>Frame</th>
            <th>Brand</th>
            <th>Category</th>
            <th className="num">Duration</th>
            <th>Ingested</th>
            <th style={{ width: 32 }} />
          </tr>
        </thead>
        <tbody>
          {ads.map((ad) => {
            const detail = details[ad.id];
            const cls = detail?.classification;
            const category = ad.primary_category ?? cls?.primary_category ?? null;
            const ar = aspectFromDims(ad.width, ad.height);
            const seed = deriveSeed(ad.id);
            return (
              <tr
                key={ad.id}
                className={selectedId === ad.id ? "selected" : ""}
                onClick={() => onSelect(ad.id)}
              >
                <td>
                  <FrameThumbnail
                    src={framePreviews?.[ad.id]}
                    ar={ar}
                    seedA={seed.seedA}
                    seedB={seed.seedB}
                  />
                </td>
                <td>
                  <div className="brand-cell">
                    <span className="name">{ad.advertiser_name || ad.brand_name || "Unknown brand"}</span>
                    <span className="sub">
                      {formatSubLine(ad)}
                    </span>
                  </div>
                </td>
                <td>
                  <CategoryBadge category={category} />
                </td>
                <td className="num mono">{formatDuration(ad.duration_ms)}</td>
                <td className="mono" title={ad.ingested_at ?? undefined}>
                  {relativeTime(ad.ingested_at)}
                </td>
                <td>
                  <ChevronRightIcon size={11} style={{ color: "var(--fg-quiet)" }} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
