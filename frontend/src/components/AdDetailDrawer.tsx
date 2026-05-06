import { Copy, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";

import { filePathToDataUrl, formatTimestamp } from "../lib/format";
import { categories, sensitiveCategories } from "../lib/taxonomy";
import type { AdDetail, FrameRecord, RelatedAds } from "../lib/types";
import { CategoryBadge } from "./shared/CategoryBadge";
import { FrameThumbnail } from "./shared/FrameThumbnail";
import { ObservationTagPill } from "./shared/ObservationTagPill";
import { SensitivePill } from "./shared/SensitivePill";
import { Button } from "./ui/Button";
import { Card, CardTitle } from "./ui/Card";
import { Input, Select } from "./ui/Form";

const tabs = ["Overview", "Evidence", "Related", "Edit"] as const;

export function AdDetailDrawer({
  detail,
  frames,
  related,
  onClose,
  onSave,
  onDelete
}: {
  detail: AdDetail;
  frames: FrameRecord[];
  related?: RelatedAds;
  onClose: () => void;
  onSave: (patch: { brand_name?: string | null; products_text?: string | null; primary_category?: string | null }) => void;
  onDelete: () => void;
}) {
  const [tab, setTab] = useState<(typeof tabs)[number]>("Overview");
  const [brand, setBrand] = useState(detail.ad.brand_name ?? "");
  const [products, setProducts] = useState(detail.ad.products_text ?? "");
  const [category, setCategory] = useState(
    detail.classification?.primary_category ?? detail.ad.primary_category ?? "other"
  );
  const entities = detail.marketing_entities?.entities;
  const classification = detail.classification;
  const categoryValue = classification?.primary_category ?? detail.ad.primary_category;

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-[680px] overflow-y-auto border-l border-border bg-background p-5 shadow-panel">
      <header className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="font-mono text-xs text-muted-foreground">{detail.ad.id}</div>
          <h2 className="mt-1 text-xl font-semibold">
            {detail.ad.brand_name || entities?.brand?.name || "Unknown brand"} · {categoryValue || "uncategorized"}
          </h2>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => navigator.clipboard.writeText(detail.ad.id)}>
            <Copy className="h-4 w-4" />
          </Button>
          <Button variant="secondary">
            <Plus className="h-4 w-4" />
            Add to campaign
          </Button>
          <Button variant="danger" onClick={onDelete}>
            <Trash2 className="h-4 w-4" />
          </Button>
          <Button variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </header>

      <video controls src={filePathToDataUrl(detail.ad.source_path)} className="mb-4 aspect-video w-full rounded-lg bg-black" />

      <div className="mb-4 flex gap-2 border-b border-border">
        {tabs.map((item) => (
          <button
            key={item}
            onClick={() => setTab(item)}
            className={`border-b-2 px-3 py-2 text-sm transition ${
              tab === item ? "border-accent text-foreground" : "border-transparent text-muted-foreground"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      {tab === "Overview" && (
        <div className="space-y-4">
          <Card>
            <CardTitle>Category</CardTitle>
            <div className="mt-3 flex items-center justify-between gap-3">
              <div className="font-mono text-lg text-violet-100">{categoryValue || "uncategorized"}</div>
              <div className="font-mono text-sm text-muted-foreground">{classification?.confidence ?? "-"}</div>
            </div>
            <div className="mt-3">
              <SensitivePill visible={sensitiveCategories.has(categoryValue ?? "")} />
            </div>
          </Card>

          <Card>
            <CardTitle>Brand & creative</CardTitle>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-muted-foreground">Brand</dt>
                <dd>{entities?.brand?.name || detail.ad.brand_name || "-"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Tagline</dt>
                <dd>{entities?.brand?.tagline || "-"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Voiceover</dt>
                <dd>{entities?.creative_format?.has_voiceover ? "Yes" : "No"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">On-screen text</dt>
                <dd>{entities?.creative_format?.has_on_screen_text ? "Yes" : "No"}</dd>
              </div>
            </dl>
          </Card>

          <Card>
            <CardTitle>Observation tags</CardTitle>
            <div className="mt-3 flex flex-wrap gap-2">
              {(classification?.risk_labels ?? []).length === 0 ? (
                <span className="text-sm text-muted-foreground">No risk tags detected.</span>
              ) : (
                classification?.risk_labels?.map((risk) => <ObservationTagPill key={risk} label={risk} />)
              )}
            </div>
          </Card>

          <Card>
            <CardTitle>Offers & CTAs</CardTitle>
            <div className="mt-3 space-y-3 text-sm">
              <div>
                <div className="text-muted-foreground">Products</div>
                <div>{entities?.products?.join(", ") || detail.ad.products_text || "-"}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Offers</div>
                {(entities?.offers ?? []).map((offer, index) => (
                  <div key={`${offer.value}-${index}`} className="rounded-md bg-muted p-2">
                    {offer.value || offer.type || "offer"}
                  </div>
                ))}
                {(entities?.offers ?? []).length === 0 && <div>-</div>}
              </div>
              <div>
                <div className="text-muted-foreground">CTAs</div>
                {(entities?.ctas ?? []).map((cta, index) => (
                  <div key={`${cta.text}-${index}`}>
                    {cta.text} <span className="font-mono text-muted-foreground">{formatTimestamp(cta.time_ms)}</span>
                  </div>
                ))}
                {(entities?.ctas ?? []).length === 0 && <div>-</div>}
              </div>
            </div>
          </Card>
        </div>
      )}

      {tab === "Evidence" && (
        <Card>
          <CardTitle>Evidence</CardTitle>
          <div className="mt-3 space-y-2">
            {(classification?.evidence ?? []).map((item, index) => (
              <div key={index} className="grid grid-cols-[5rem_4.5rem_1fr] gap-3 rounded-md bg-muted p-2 text-sm">
                <FrameThumbnail path={frames.find((frame) => frame.frame_index === item.frame_index)?.path} />
                <div className="font-mono text-xs text-muted-foreground">{formatTimestamp(item.time_ms)}</div>
                <div>
                  <div>{item.text}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{item.source} · {item.reason}</div>
                </div>
              </div>
            ))}
            {(classification?.evidence ?? []).length === 0 && <p className="text-sm text-muted-foreground">No evidence stored.</p>}
          </div>
        </Card>
      )}

      {tab === "Related" && (
        <Card>
          <CardTitle>Related ads</CardTitle>
          <div className="mt-3 space-y-2">
            {(related?.semantically_similar ?? []).map((item) => (
              <div key={item.ad_id} className="rounded-md border border-border bg-muted p-3">
                <div className="font-mono text-sm">{item.ad_id}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  overall {item.overall_score ?? "-"} · text {item.text_score ?? "-"} · visual {item.visual_score ?? "-"}
                </div>
                <div className="mt-2">
                  <CategoryBadge category={item.verdict || "similar"} />
                </div>
              </div>
            ))}
            {(related?.semantically_similar ?? []).length === 0 && <p className="text-sm text-muted-foreground">No related ads indexed yet.</p>}
          </div>
        </Card>
      )}

      {tab === "Edit" && (
        <Card>
          <CardTitle>Edit curated fields</CardTitle>
          <div className="mt-4 space-y-3">
            <Input value={brand} onChange={(event) => setBrand(event.target.value)} placeholder="Brand" className="w-full" />
            <Input value={products} onChange={(event) => setProducts(event.target.value)} placeholder="Products" className="w-full" />
            <Select value={category} onChange={(event) => setCategory(event.target.value)} className="w-full">
              {categories.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
            <Button variant="primary" onClick={() => onSave({ brand_name: brand, products_text: products, primary_category: category })}>
              Save changes
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
