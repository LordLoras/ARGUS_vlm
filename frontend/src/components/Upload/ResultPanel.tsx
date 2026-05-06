import { Link } from "react-router-dom";

import { filePathToDataUrl, formatTimestamp } from "../../lib/format";
import { sensitiveCategories } from "../../lib/taxonomy";
import type { AdDetail, FrameRecord, RelatedAds } from "../../lib/types";
import { CategoryBadge } from "../shared/CategoryBadge";
import { FrameThumbnail } from "../shared/FrameThumbnail";
import { ObservationTagPill } from "../shared/ObservationTagPill";
import { SensitivePill } from "../shared/SensitivePill";
import { Button } from "../ui/Button";
import { Card, CardTitle } from "../ui/Card";

export function ResultPanel({
  detail,
  frames,
  related,
  onReset
}: {
  detail: AdDetail;
  frames: FrameRecord[];
  related?: RelatedAds;
  onReset: () => void;
}) {
  const entities = detail.marketing_entities?.entities;
  const classification = detail.classification;
  const category = classification?.primary_category ?? detail.ad.primary_category;

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle>Result</CardTitle>
        <div className="mt-3 flex items-center justify-between">
          <div className="font-mono text-2xl text-violet-100">{category || "uncategorized"}</div>
          <div className="font-mono text-muted-foreground">{classification?.confidence ?? "-"}</div>
        </div>
        <div className="mt-3">
          <SensitivePill visible={sensitiveCategories.has(category ?? "")} />
        </div>
      </Card>

      <video controls src={filePathToDataUrl(detail.ad.source_path)} className="aspect-video w-full rounded-lg bg-black" />

      <Card>
        <CardTitle>Brand & products</CardTitle>
        <div className="mt-3 text-sm">
          <div>{entities?.brand?.name || detail.ad.brand_name || "Unknown brand"}</div>
          <div className="mt-2 text-muted-foreground">{entities?.products?.join(", ") || detail.ad.products_text || "No products stored."}</div>
        </div>
      </Card>

      <Card>
        <CardTitle>Offers & CTAs</CardTitle>
        <div className="mt-3 space-y-2 text-sm">
          {(entities?.offers ?? []).map((offer, index) => (
            <div key={`${offer.value}-${index}`}>{offer.value || offer.type}</div>
          ))}
          {(entities?.ctas ?? []).map((cta, index) => (
            <div key={`${cta.text}-${index}`}>
              {cta.text} <span className="font-mono text-muted-foreground">{formatTimestamp(cta.time_ms)}</span>
            </div>
          ))}
          {(entities?.offers ?? []).length === 0 && (entities?.ctas ?? []).length === 0 && <div className="text-muted-foreground">No offers or CTAs stored.</div>}
        </div>
      </Card>

      <Card>
        <CardTitle>Observation tags</CardTitle>
        <div className="mt-3 flex flex-wrap gap-2">
          {(classification?.risk_labels ?? []).length === 0 ? (
            <span className="text-sm text-muted-foreground">No observation tags.</span>
          ) : (
            classification?.risk_labels?.map((risk) => <ObservationTagPill key={risk} label={risk} />)
          )}
        </div>
      </Card>

      <Card>
        <CardTitle>Evidence highlights</CardTitle>
        <div className="mt-3 space-y-2">
          {(classification?.evidence ?? []).slice(0, 3).map((item, index) => (
            <div key={index} className="grid grid-cols-[5rem_1fr] gap-3 rounded-md bg-muted p-2 text-sm">
              <FrameThumbnail path={frames.find((frame) => frame.frame_index === item.frame_index)?.path} />
              <div>
                <div>{item.text}</div>
                <div className="mt-1 font-mono text-xs text-muted-foreground">{formatTimestamp(item.time_ms)} · {item.source}</div>
              </div>
            </div>
          ))}
          {(classification?.evidence ?? []).length === 0 && <div className="text-sm text-muted-foreground">No evidence highlights stored.</div>}
        </div>
      </Card>

      <Card>
        <CardTitle>Related ads</CardTitle>
        <div className="mt-3 space-y-2">
          {(related?.semantically_similar ?? []).slice(0, 3).map((item) => (
            <div key={item.ad_id} className="rounded-md bg-muted p-3">
              <div className="font-mono">{item.ad_id}</div>
              <CategoryBadge category={item.verdict || "similar"} />
            </div>
          ))}
          {(related?.semantically_similar ?? []).length === 0 && <div className="text-sm text-muted-foreground">No related ads yet.</div>}
        </div>
      </Card>

      <div className="flex gap-3">
        <Link to="/library" className="inline-flex h-9 items-center rounded-md bg-accent px-3 text-sm font-medium text-accent-foreground">
          Open full detail
        </Link>
        <Button onClick={onReset}>Upload another</Button>
      </div>
    </div>
  );
}
