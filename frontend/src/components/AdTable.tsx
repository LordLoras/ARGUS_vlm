import { ArrowDownUp } from "lucide-react";

import { formatDuration, relativeTime } from "../lib/format";
import { sensitiveCategories } from "../lib/taxonomy";
import type { AdDetail, AdRecord } from "../lib/types";
import { CategoryBadge } from "./shared/CategoryBadge";
import { ConfidenceBar } from "./shared/ConfidenceBar";
import { ObservationTagPill } from "./shared/ObservationTagPill";
import { SensitivePill } from "./shared/SensitivePill";

export function AdTable({
  ads,
  details,
  onSelect
}: {
  ads: AdRecord[];
  details: Record<string, AdDetail | undefined>;
  onSelect: (adId: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface/80">
      <table className="w-full table-fixed border-collapse text-sm">
        <thead className="bg-muted/60 text-xs uppercase text-muted-foreground">
          <tr>
            <th className="w-40 px-4 py-3 text-left">Ad</th>
            <th className="px-4 py-3 text-left">
              <span className="inline-flex items-center gap-1">
                Brand <ArrowDownUp className="h-3 w-3" />
              </span>
            </th>
            <th className="w-52 px-4 py-3 text-left">Category</th>
            <th className="w-36 px-4 py-3 text-left">Confidence</th>
            <th className="w-60 px-4 py-3 text-left">Risk tags</th>
            <th className="w-24 px-4 py-3 text-right">Duration</th>
            <th className="w-28 px-4 py-3 text-right">Ingested</th>
          </tr>
        </thead>
        <tbody>
          {ads.map((ad) => {
            const classification = details[ad.id]?.classification;
            const risks = classification?.risk_labels ?? [];
            const category = classification?.primary_category ?? ad.primary_category;
            return (
              <tr
                key={ad.id}
                onClick={() => onSelect(ad.id)}
                className="cursor-pointer border-t border-border/70 transition hover:bg-muted/40"
              >
                <td className="px-4 py-3">
                  <div className="font-mono text-xs text-violet-100">{ad.id}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{ad.status ?? "unknown"}</div>
                </td>
                <td className="truncate px-4 py-3">{ad.brand_name || "Unknown brand"}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <CategoryBadge category={category} />
                    <SensitivePill visible={sensitiveCategories.has(category ?? "")} />
                  </div>
                </td>
                <td className="px-4 py-3">
                  <ConfidenceBar value={classification?.confidence} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {risks.length === 0 ? (
                      <span className="text-muted-foreground">-</span>
                    ) : (
                      <>
                        {risks.slice(0, 2).map((risk) => (
                          <ObservationTagPill key={risk} label={risk} />
                        ))}
                        {risks.length > 2 && <span className="text-xs text-muted-foreground">+{risks.length - 2}</span>}
                      </>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-right font-mono text-xs">{formatDuration(ad.duration_ms)}</td>
                <td className="px-4 py-3 text-right text-xs text-muted-foreground">{relativeTime(ad.ingested_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
