import type { CSSProperties } from "react";

import type { Campaign } from "../../lib/types";
import { deriveSeed } from "../../lib/style-helpers";

export function CampaignCard({
  campaign,
  count,
  meanSimilarity,
  range
}: {
  campaign: Campaign;
  count?: number;
  meanSimilarity?: number;
  range?: string;
}) {
  const seeds = deriveSeed(campaign.id);
  const cells: CSSProperties[] = Array.from({ length: 4 }).map((_, i) => ({
    "--seed-a": shift(seeds.seedA, i),
    "--seed-b": shift(seeds.seedB, i)
  }) as CSSProperties);
  return (
    <article className="cam-card">
      <div className="cam-card-head">
        <div style={{ flex: 1, minWidth: 0 }}>
          <span className="name">{campaign.name}</span>
          <span className="id">{campaign.id}</span>
        </div>
        <span className={`badge ${campaign.created_by === "auto" ? "badge-violet" : ""}`}>
          {campaign.created_by ?? "user"}
        </span>
      </div>
      <div className="cam-mosaic">
        {cells.map((style, idx) =>
          idx === 3 && (count ?? 0) > 4 ? (
            <div key={idx} className="cam-mosaic-cell more">
              +{(count ?? 0) - 3}
            </div>
          ) : (
            <div key={idx} className="cam-mosaic-cell" style={style} />
          )
        )}
      </div>
      <div className="cam-card-body">
        <div className="cam-stats">
          <div>
            <div className="label">Ads</div>
            <div className="val">{count ?? "—"}</div>
          </div>
          <div>
            <div className="label">Mean similarity</div>
            <div className="val">{meanSimilarity != null ? meanSimilarity.toFixed(2) : "—"}</div>
          </div>
          <div>
            <div className="label">Date range</div>
            <div className="val mono" style={{ fontSize: 11 }}>{range ?? "—"}</div>
          </div>
        </div>
        <div className="cam-row">
          <span className="badge badge-mono">{campaign.brand ?? "—"}</span>
          {campaign.theme ? <span className="badge">{campaign.theme}</span> : null}
        </div>
      </div>
    </article>
  );
}

function shift(hex: string, i: number) {
  const n = parseInt(hex.slice(1), 16);
  const delta = (i + 1) * 0x080808;
  const next = (n + delta) & 0xffffff;
  return `#${next.toString(16).padStart(6, "0")}`;
}
