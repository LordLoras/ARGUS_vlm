import { ChevronDownIcon, ChevronRightIcon } from "../lib/icons";
import { formatDuration, relativeTime } from "../lib/format";
import { aspectFromDims, deriveSeed } from "../lib/style-helpers";
import type { AdDetail, AdRecord } from "../lib/types";
import { CategoryBadge } from "./shared/CategoryBadge";
import { ConfidenceBar } from "./shared/ConfidenceBar";
import { FrameThumbnail } from "./shared/FrameThumbnail";
import { ObservationTagOverflow, ObservationTagPill } from "./shared/ObservationTagPill";

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
            <th className="sortable">
              Confidence <ChevronDownIcon size={9} className="sort-arrow" />
            </th>
            <th>Risk tags</th>
            <th className="num">Duration</th>
            <th className="sortable">
              Ingested <ChevronDownIcon size={9} className="sort-arrow" />
            </th>
            <th style={{ width: 32 }} />
          </tr>
        </thead>
        <tbody>
          {ads.map((ad) => {
            const detail = details[ad.id];
            const cls = detail?.classification;
            const category = ad.primary_category ?? cls?.primary_category ?? null;
            const risks = cls?.risk_labels ?? [];
            const confidence = cls?.confidence ?? ad.brand_confidence ?? null;
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
                      {[ad.brand_name, ad.promotion_name].filter(Boolean).join(" / ") || ad.id}
                    </span>
                  </div>
                </td>
                <td>
                  <CategoryBadge category={category} />
                </td>
                <td>
                  <ConfidenceBar value={confidence} />
                </td>
                <td>
                  <div className="risk-cell">
                    {risks.length === 0 ? (
                      <span className="obs-empty">—</span>
                    ) : (
                      <>
                        {risks.slice(0, 2).map((label) => (
                          <ObservationTagPill key={label} label={label} />
                        ))}
                        {risks.length > 2 ? (
                          <ObservationTagOverflow count={risks.length - 2} />
                        ) : null}
                      </>
                    )}
                  </div>
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
