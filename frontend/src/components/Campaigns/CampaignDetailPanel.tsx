import { useState, type ReactNode } from "react";
import { Clock3, Megaphone, Package, Tags } from "lucide-react";

import { EditIcon, PlusIcon, TrashIcon, XIcon } from "../../lib/icons";
import { formatDuration } from "../../lib/format";
import type {
  CampaignAd,
  Campaign,
  CampaignCount,
  CampaignDeepResearch,
  CampaignDetail,
  CampaignInsight,
  CampaignProductFamily,
  CampaignResearch
} from "../../lib/types";
import { CampaignAgentPanel } from "./CampaignAgentPanel";
import { emptyResearch, formatRange, formatScore } from "./campaignDetailUtils";

const TABS = ["Overview", "Ads", "Research", "Agent"] as const;
type CampaignTab = (typeof TABS)[number];

export function CampaignDetailPanel({
  detail,
  deepResearch,
  loading,
  researchLoading,
  onEdit,
  onDelete,
  onAssign,
  onUnassign,
  onRunDeepResearch,
  assigning,
  unassigningAdId
}: {
  detail?: CampaignDetail;
  deepResearch?: CampaignDeepResearch;
  loading?: boolean;
  researchLoading?: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onAssign: (adIds: string[]) => void;
  onUnassign: (adId: string) => void;
  onRunDeepResearch: (question?: string) => void;
  assigning?: boolean;
  unassigningAdId?: string | null;
}) {
  const [tab, setTab] = useState<CampaignTab>("Overview");
  const [adIdsText, setAdIdsText] = useState("");

  if (loading) {
    return <div className="campaign-detail-shell obs-empty">Loading campaign detail…</div>;
  }

  if (!detail) {
    return (
      <div className="campaign-detail-shell empty">
        <div className="empty-block">
          <div className="hint">Select a campaign to inspect assignments and research signals.</div>
        </div>
      </div>
    );
  }

  const campaign = detail.campaign;
  const ads = detail.ads ?? [];
  const research = detail.research ?? emptyResearch(ads.length);

  const submitAssignment = () => {
    const adIds = adIdsText
      .split(/[\s,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (!adIds.length) return;
    onAssign(Array.from(new Set(adIds)));
    setAdIdsText("");
  };

  return (
    <section className="campaign-detail-shell">
      <header className="campaign-detail-head compact">
        <div>
          <div className="campaign-kicker">
            <span className="badge badge-mono">{campaign.created_by ?? "user"}</span>
            <span className="mono">{campaign.id}</span>
          </div>
          <h2>{campaign.name}</h2>
          <p>
            {[campaign.brand, campaign.advertiser, campaign.theme].filter(Boolean).join(" / ") ||
              "No brand, advertiser, or theme metadata"}
          </p>
        </div>
        <div className="campaign-actions">
          <button className="btn btn-sm" onClick={onEdit}>
            <EditIcon size={11} />
            <span>Edit</span>
          </button>
          <button className="btn btn-sm btn-danger" onClick={onDelete}>
            <TrashIcon size={11} />
            <span>Delete</span>
          </button>
        </div>
      </header>

      <div className="campaign-metrics compact">
        <Metric
          label="Ads"
          value={String(research.summary.ad_count)}
          sub={`${research.summary.user_assigned ?? 0} user / ${research.summary.auto_assigned ?? 0} auto`}
          help="Total assigned ads, split between manual assignments and auto-discovered assignments."
        />
        <Metric
          label="Campaign fit"
          value={formatScore(research.summary.mean_similarity)}
          sub="how tightly ads group"
          help="Mean assignment similarity across ads in this campaign. Higher means the ads look and read more like one campaign."
        />
        <Metric
          label="Evidence trust"
          value={formatScore(research.summary.avg_confidence)}
          sub={
            research.summary.min_confidence != null
              ? `lowest ${formatScore(research.summary.min_confidence)}`
              : "entity quality"
          }
          help="Average classifier confidence for assigned ads. The sublabel shows the weakest ad when available."
        />
        <Metric
          label="Run window"
          value={research.summary.span_days != null ? `${research.summary.span_days}d` : "-"}
          sub={formatRange(research.summary.first_seen, research.summary.last_seen)}
          help="Date range covered by the ads currently assigned to this campaign."
        />
      </div>

      <div className="campaign-tabs">
        {TABS.map((label) => (
          <button key={label} className={tab === label ? "active" : ""} onClick={() => setTab(label)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "Overview" ? (
        <OverviewTab
          campaign={campaign}
          ads={ads}
          research={research}
        />
      ) : null}

      {tab === "Ads" ? (
        <AdsTab
          ads={ads}
          adIdsText={adIdsText}
          assigning={assigning}
          unassigningAdId={unassigningAdId}
          onTextChange={setAdIdsText}
          onSubmit={submitAssignment}
          onUnassign={onUnassign}
        />
      ) : null}

      {tab === "Research" ? <ResearchTab research={research} /> : null}

      {tab === "Agent" ? (
        <CampaignAgentPanel
          deepResearch={deepResearch}
          loading={researchLoading}
          onRunDeepResearch={onRunDeepResearch}
        />
      ) : null}
    </section>
  );
}

function OverviewTab({
  campaign,
  ads,
  research
}: {
  campaign: Campaign;
  ads: CampaignAd[];
  research: CampaignResearch;
}) {
  const insights = research.insights.slice(0, 3);
  const runtimeBuckets = (research.creative.runtime_buckets?.length
    ? research.creative.runtime_buckets
    : buildRuntimeBucketsFromAds(ads));
  const productFamilies = (research.messaging.product_families?.length
    ? research.messaging.product_families
    : fallbackProductFamilies(research.messaging.top_products));
  const topOffer = research.messaging.top_offers[0];
  const topCta = research.messaging.top_ctas[0];
  const topPrice = research.messaging.top_prices[0];
  const topObservation = research.watchouts.risk_labels[0];
  const leadSignal = research.messaging.campaign_signals[0];
  const leadProduct = productFamilies[0];
  const runtimeLabel = runtimeBuckets.length
    ? runtimeBuckets.map((bucket) => `${bucket.value} ${bucket.count}`).join(" / ")
    : "No runtime split";

  return (
    <div className="campaign-tab-pane campaign-overview">
      <section className="campaign-command-center">
        <div className="campaign-command-copy">
          <span className="overview-eyebrow">Campaign read</span>
          <h3>{leadSignal?.value ?? campaign.theme ?? campaign.name}</h3>
          <p>{buildCampaignRead(research, leadProduct, topOffer, topCta)}</p>
          <div className="campaign-command-tags">
            <SignalPill label="Offer" value={topOffer?.value} count={topOffer?.count} />
            <SignalPill label="CTA" value={topCta?.value} count={topCta?.count} />
            <SignalPill label="Lead product" value={leadProduct?.value} count={leadProduct?.ad_count ?? leadProduct?.count} />
            <SignalPill label="Runtime" value={runtimeLabel} />
          </div>
        </div>
      </section>

      <div className="campaign-overview-grid">
        <section className="campaign-brief-panel campaign-brief-panel-large">
          <PanelTitle icon={<Package size={14} />} title="Product Mix" detail="Collapsed model-year variants" />
          <ProductExposure families={productFamilies} />
        </section>

        <section className="campaign-brief-panel">
          <PanelTitle icon={<Megaphone size={14} />} title="Message Stack" detail="Repeated response signals" />
          <MessageStack
            offer={topOffer}
            cta={topCta}
            price={topPrice}
            observation={topObservation}
            offers={research.messaging.top_offers}
            ctas={research.messaging.top_ctas}
            prices={research.messaging.top_prices}
          />
        </section>

        <section className="campaign-brief-panel">
          <PanelTitle icon={<Clock3 size={14} />} title="Runtime" detail="Finished cut length" />
          <RuntimeMix buckets={runtimeBuckets} totalAds={research.summary.ad_count} />
        </section>

        <section className="campaign-brief-panel campaign-brief-panel-wide">
          <PanelTitle icon={<Tags size={14} />} title="Executive Read" detail="Auto-generated campaign patterns" />
          <InsightList insights={insights} compact />
        </section>
      </div>
    </div>
  );
}

function SignalPill({
  label,
  value,
  count
}: {
  label: string;
  value?: string | null;
  count?: number | null;
}) {
  return (
    <span className="campaign-signal-pill">
      <b>{label}</b>
      <em>{value || "-"}</em>
      {count != null ? <i>{count}</i> : null}
    </span>
  );
}

function PanelTitle({
  icon,
  title,
  detail
}: {
  icon: ReactNode;
  title: string;
  detail: string;
}) {
  return (
    <div className="campaign-panel-title">
      <span>{icon}</span>
      <div>
        <strong>{title}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

function buildCampaignRead(
  research: CampaignResearch,
  leadProduct?: CampaignProductFamily,
  topOffer?: CampaignCount,
  topCta?: CampaignCount
) {
  const parts = [
    `${formatUnit(research.summary.ad_count, "assigned ad")}`,
    leadProduct ? `${leadProduct.value} leads product exposure` : null,
    topOffer ? `${topOffer.value} is the dominant offer` : null,
    topCta ? `${topCta.value} is the strongest CTA` : null
  ].filter(Boolean);
  return parts.join(". ") + ".";
}

function RuntimeMix({ buckets, totalAds }: { buckets: CampaignCount[]; totalAds: number }) {
  if (!buckets.length) {
    return <div className="obs-empty">No runtime metadata available.</div>;
  }
  const denominator = Math.max(totalAds, buckets.reduce((sum, item) => sum + item.count, 0), 1);
  const maxCount = Math.max(...buckets.map((item) => item.count), 1);
  return (
    <div className="campaign-runtime-list">
      {buckets.map((bucket) => {
        const percent = Math.round((bucket.count / denominator) * 100);
        const width = Math.max(8, Math.round((bucket.count / maxCount) * 100));
        return (
          <div key={bucket.value} className="campaign-runtime-row">
            <div>
              <strong>{bucket.value}</strong>
              <span>{formatUnit(bucket.count, "ad")}</span>
            </div>
            <div className="campaign-runtime-track" aria-hidden="true">
              <span style={{ width: `${width}%` }} />
            </div>
            <small>{bucket.share != null ? `${Math.round(bucket.share * 100)}%` : `${percent}%`}</small>
          </div>
        );
      })}
    </div>
  );
}

function ProductExposure({ families }: { families: CampaignProductFamily[] }) {
  if (!families.length) {
    return <div className="obs-empty">No product entities detected for this campaign.</div>;
  }
  const maxCount = Math.max(...families.map((family) => family.count), 1);
  const visible = families.slice(0, 4);
  return (
    <div className="campaign-product-list">
      {visible.map((family) => (
        <div key={family.value} className="campaign-product-row">
          <div className="campaign-product-main">
            <strong>{family.value}</strong>
            <span>
              {formatUnit(family.count, "mention")} / {formatUnit(family.ad_count ?? family.count, "ad")}
              {family.total_duration_ms ? ` / ${formatShortDuration(family.total_duration_ms)} runtime` : ""}
            </span>
          </div>
          <div className="campaign-product-bar" aria-hidden="true">
            <span style={{ width: `${Math.max(10, Math.round((family.count / maxCount) * 100))}%` }} />
          </div>
          {family.variants?.length ? (
            <div className="campaign-product-variants">
              {family.variants.slice(0, 3).map((variant) => (
                <span key={variant.value}>
                  {variant.value} <b>{variant.count}</b>
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ))}
      {families.length > visible.length ? (
        <div className="campaign-more-row">+{families.length - visible.length} more product families</div>
      ) : null}
    </div>
  );
}

function MessageStack({
  offer,
  cta,
  price,
  observation,
  offers,
  ctas,
  prices
}: {
  offer?: CampaignCount;
  cta?: CampaignCount;
  price?: CampaignCount;
  observation?: CampaignCount;
  offers: CampaignCount[];
  ctas: CampaignCount[];
  prices: CampaignCount[];
}) {
  return (
    <div className="campaign-message-stack">
      <MessageLead label="Offer" item={offer} />
      <MessageLead label="CTA" item={cta} />
      <MessageLead label="Price" item={price} />
      <MessageLead label="Observation" item={observation} empty="No repeated tags" />
      <div className="campaign-message-evidence">
        {[...offers.slice(0, 2), ...ctas.slice(0, 2), ...prices.slice(0, 2)].map((item) => (
          <span key={`${item.value}-${item.count}`}>
            {item.value} <b>{item.count}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

function MessageLead({
  label,
  item,
  empty = "-"
}: {
  label: string;
  item?: CampaignCount;
  empty?: string;
}) {
  return (
    <div className="campaign-message-lead">
      <span>{label}</span>
      <strong>{item?.value ?? empty}</strong>
      {item ? <small>{formatUnit(item.count, "ad")}</small> : null}
    </div>
  );
}

function AdsTab({
  ads,
  adIdsText,
  assigning,
  unassigningAdId,
  onTextChange,
  onSubmit,
  onUnassign
}: {
  ads: CampaignAd[];
  adIdsText: string;
  assigning?: boolean;
  unassigningAdId?: string | null;
  onTextChange: (value: string) => void;
  onSubmit: () => void;
  onUnassign: (adId: string) => void;
}) {
  return (
    <section className="campaign-tab-pane campaign-section first">
      <div className="campaign-section-head">
        <div className="section-title">Assigned ads</div>
        <div className="campaign-ad-add">
          <input
            className="input mono"
            value={adIdsText}
            onChange={(event) => onTextChange(event.target.value)}
            placeholder="ad_id, ad_id"
          />
          <button className="btn btn-sm" onClick={onSubmit} disabled={!adIdsText.trim() || assigning}>
            <PlusIcon size={11} />
            <span>Add</span>
          </button>
        </div>
      </div>
      <div className="campaign-ad-table">
        {ads.length === 0 ? (
          <div className="obs-empty" style={{ padding: 16 }}>No ads assigned.</div>
        ) : (
          ads.map((ad) => (
            <AdRow
              key={ad.ad_id}
              ad={ad}
              onUnassign={onUnassign}
              unassigning={unassigningAdId === ad.ad_id}
            />
          ))
        )}
      </div>
    </section>
  );
}

function ResearchTab({ research }: { research: CampaignResearch }) {
  return (
    <div className="campaign-tab-pane">
      <div className="campaign-research-grid">
        <section className="campaign-section first">
          <div className="section-title">Message stack</div>
          <CountList title="Products" items={research.messaging.top_products} />
          <CountList title="Product families" items={research.messaging.product_families ?? []} />
          <CountList title="Offers" items={research.messaging.top_offers} />
          <CountList title="CTAs" items={research.messaging.top_ctas} />
          <CountList title="Campaign language" items={research.messaging.campaign_signals} />
        </section>

        <section className="campaign-section first">
          <div className="section-title">Creative footprint</div>
          <CountList title="Runtime cuts" items={research.creative.runtime_buckets ?? []} />
          <CountList title="Brands" items={research.summary.brands} />
          <CountList title="Categories" items={research.summary.categories} />
          <CountList title="Observation tags" items={research.watchouts.risk_labels} />
          <div className="campaign-creative-strip">
            <span>{research.creative.voiceover_ads} voiceover</span>
            <span>{research.creative.on_screen_text_ads} text-heavy</span>
            <span>{research.creative.disclaimer_ads} disclaimers</span>
            <span>{research.creative.small_print_ads} small print</span>
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  help
}: {
  label: string;
  value: string;
  sub: string;
  help?: string;
}) {
  return (
    <div
      className="campaign-metric"
      title={help}
      aria-label={help ? `${label}: ${help}` : undefined}
      tabIndex={help ? 0 : undefined}
    >
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function InsightList({ insights, compact }: { insights: CampaignInsight[]; compact?: boolean }) {
  if (!insights.length) {
    return <div className="obs-empty">No strong campaign-level patterns yet.</div>;
  }
  return (
    <div className={`insight-list ${compact ? "compact" : ""}`}>
      {insights.map((insight) => (
        <div key={`${insight.title}-${insight.detail}`} className="insight-row">
          <span>{insight.title}</span>
          <p>{insight.detail}</p>
        </div>
      ))}
    </div>
  );
}

function CountList({ title, items }: { title: string; items: CampaignCount[] }) {
  return (
    <div className="count-block">
      <span className="count-title">{title}</span>
      {items.length === 0 ? (
        <span className="count-empty">-</span>
      ) : (
        <div className="count-list">
          {items.slice(0, 4).map((item) => (
            <span key={item.value}>
              <b>{item.value}</b>
              <em>{item.count}</em>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function fallbackProductFamilies(items: CampaignCount[]): CampaignProductFamily[] {
  return items.map((item) => ({
    ...item,
    ad_count: item.count,
    variants: [item]
  }));
}

function buildRuntimeBucketsFromAds(ads: CampaignAd[]): CampaignCount[] {
  const counts = new Map<string, number>();
  ads.forEach((ad) => {
    const seconds = ad.duration_ms ? Math.round(ad.duration_ms / 1000) : null;
    const value = seconds ? `${seconds}s` : "Unknown";
    counts.set(value, (counts.get(value) ?? 0) + 1);
  });
  const total = ads.length || Array.from(counts.values()).reduce((sum, count) => sum + count, 0);
  return Array.from(counts.entries())
    .sort(([left], [right]) => runtimeSortKey(left) - runtimeSortKey(right))
    .map(([value, count]) => ({
      value,
      count,
      share: total ? count / total : 0
    }));
}

function runtimeSortKey(value: string) {
  if (value === "Unknown") return Number.MAX_SAFE_INTEGER;
  const parsed = Number(value.replace(/s$/, ""));
  return Number.isFinite(parsed) ? parsed : Number.MAX_SAFE_INTEGER - 1;
}

function formatShortDuration(ms?: number | null) {
  if (!ms) return "-";
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  return formatDuration(ms);
}

function formatUnit(count: number, unit: string) {
  return `${count} ${count === 1 ? unit : `${unit}s`}`;
}

function AdRow({
  ad,
  onUnassign,
  unassigning
}: {
  ad: CampaignAd;
  onUnassign: (adId: string) => void;
  unassigning?: boolean;
}) {
  const products = ad.products?.length ? ad.products.join(", ") : ad.products_text;
  return (
    <div className="campaign-ad-row">
      <div>
        <span className="mono">{ad.ad_id}</span>
        <small>{[ad.brand_name, ad.primary_category, products].filter(Boolean).join(" / ") || "No ad metadata"}</small>
      </div>
      <span className="badge badge-mono">{ad.assigned_by ?? "user"}</span>
      <span className="mono score">{formatScore(ad.similarity_score)}</span>
      <button
        className="btn btn-sm btn-icon btn-ghost"
        title="Remove from campaign"
        onClick={() => onUnassign(ad.ad_id)}
        disabled={unassigning}
      >
        <XIcon size={11} />
      </button>
    </div>
  );
}
