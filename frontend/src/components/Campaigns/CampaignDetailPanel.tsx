import { useState, type ReactNode } from "react";
import { Clock3, Megaphone, MousePointerClick, Package, Tags } from "lucide-react";

import { EditIcon, PlusIcon, TrashIcon, XIcon } from "../../lib/icons";
import { formatDuration } from "../../lib/format";
import type {
  CampaignAd,
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
          ads={ads}
          research={research}
          description={campaign.description}
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
  ads,
  research,
  description
}: {
  ads: CampaignAd[];
  research: CampaignResearch;
  description?: string | null;
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

  return (
    <div className="campaign-tab-pane campaign-overview">
      <section className="campaign-overview-band">
        <div>
          <span className="overview-eyebrow">Overview</span>
          <h3>Run mix, product exposure, and response signals</h3>
          {description ? <p>{description}</p> : <p>Campaign-level rollup from assigned ads and extracted marketing entities.</p>}
        </div>
        <div className="overview-score-row">
          <OverviewScore label="Assigned ads" value={String(research.summary.ad_count)} />
          <OverviewScore
            label="Runtime cuts"
            value={String(runtimeBuckets.filter((item) => item.value !== "Unknown").length)}
          />
          <OverviewScore label="Product families" value={String(productFamilies.length)} />
          <OverviewScore label="Signal confidence" value={formatScore(research.summary.avg_confidence)} />
        </div>
      </section>

      <section className="campaign-overview-section runtime-section">
        <SectionHeader
          icon={<Clock3 size={15} />}
          title="Runtime mix"
          detail="Count of assigned ads by finished cut length."
        />
        <RuntimeMix buckets={runtimeBuckets} totalAds={research.summary.ad_count} />
      </section>

      <section className="campaign-overview-section">
        <SectionHeader
          icon={<Package size={15} />}
          title="Product exposure"
          detail="Model-year prefixes are collapsed so 2025 and 2026 variants roll up together."
        />
        <ProductExposure families={productFamilies} />
      </section>

      <section className="campaign-overview-section">
        <SectionHeader
          icon={<Megaphone size={15} />}
          title="Message leaders"
          detail="The strongest repeated offer, CTA, price, and observation signals."
        />
        <div className="campaign-leader-grid">
          <LeaderCard
            icon={<Tags size={14} />}
            label="Top offer"
            item={topOffer}
            empty="No repeated offer"
            items={research.messaging.top_offers}
          />
          <LeaderCard
            icon={<MousePointerClick size={14} />}
            label="Top CTA"
            item={topCta}
            empty="No repeated CTA"
            items={research.messaging.top_ctas}
          />
          <LeaderCard
            icon={<Tags size={14} />}
            label="Top price"
            item={topPrice}
            empty="No price signal"
            items={research.messaging.top_prices}
          />
          <LeaderCard
            icon={<Tags size={14} />}
            label="Observation"
            item={topObservation}
            empty="No repeated tags"
            items={research.watchouts.risk_labels}
          />
        </div>
      </section>

      <section className="campaign-overview-section">
        <SectionHeader
          icon={<Tags size={15} />}
          title="Executive read"
          detail="Automatically generated campaign-level patterns."
        />
        <InsightList insights={insights} compact />
      </section>
    </div>
  );
}

function SectionHeader({
  icon,
  title,
  detail
}: {
  icon: ReactNode;
  title: string;
  detail: string;
}) {
  return (
    <div className="campaign-overview-section-head">
      <span className="campaign-overview-icon">{icon}</span>
      <div>
        <div className="section-title">{title}</div>
        <p>{detail}</p>
      </div>
    </div>
  );
}

function OverviewScore({ label, value }: { label: string; value: string }) {
  return (
    <div className="overview-score">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RuntimeMix({ buckets, totalAds }: { buckets: CampaignCount[]; totalAds: number }) {
  if (!buckets.length) {
    return <div className="obs-empty">No runtime metadata available.</div>;
  }
  const denominator = Math.max(totalAds, buckets.reduce((sum, item) => sum + item.count, 0), 1);
  const maxCount = Math.max(...buckets.map((item) => item.count));
  return (
    <div className="runtime-mix-grid">
      {buckets.map((bucket) => {
        const percent = Math.max(6, Math.round((bucket.count / denominator) * 100));
        return (
          <details key={bucket.value} className="runtime-cut" open={bucket.count === maxCount}>
            <summary>
              <span className="runtime-cut-length">{bucket.value}</span>
              <span className="runtime-cut-count">{bucket.count} ads</span>
            </summary>
            <div className="runtime-cut-track" aria-hidden="true">
              <span style={{ width: `${percent}%` }} />
            </div>
            <p>
              {bucket.share != null ? `${Math.round(bucket.share * 100)}% of assigned ads` : "Share unavailable"} in this cut length.
            </p>
          </details>
        );
      })}
    </div>
  );
}

function ProductExposure({ families }: { families: CampaignProductFamily[] }) {
  if (!families.length) {
    return <div className="obs-empty">No product entities detected for this campaign.</div>;
  }
  return (
    <div className="product-exposure-grid">
      {families.slice(0, 6).map((family, index) => (
        <details key={family.value} className="product-exposure" open={index < 2}>
          <summary>
            <span className="product-name">{family.value}</span>
            <span className="product-stats">
              <b>{family.count}</b> mentions
              <em>{family.ad_count ?? family.count} ads</em>
              <em>{formatShortDuration(family.total_duration_ms)} runtime</em>
            </span>
          </summary>
          <div className="product-exposure-body">
            <CountList title="Variants" items={family.variants ?? []} />
            {family.ad_ids?.length ? (
              <div className="product-ad-ids">
                <span>Ads</span>
                <p className="mono">{family.ad_ids.slice(0, 8).join(", ")}</p>
              </div>
            ) : null}
          </div>
        </details>
      ))}
    </div>
  );
}

function LeaderCard({
  icon,
  label,
  item,
  empty,
  items
}: {
  icon: ReactNode;
  label: string;
  item?: CampaignCount;
  empty: string;
  items: CampaignCount[];
}) {
  return (
    <details className="leader-card" open={Boolean(item)}>
      <summary>
        <span className="leader-icon">{icon}</span>
        <span className="leader-copy">
          <small>{label}</small>
          <strong>{item?.value ?? "-"}</strong>
        </span>
        <span className="leader-count">{item ? `${item.count} ads` : empty}</span>
      </summary>
      {items.length ? (
        <div className="leader-detail-list">
          {items.slice(0, 6).map((value) => (
            <span key={value.value}>
              <b>{value.value}</b>
              <em>{value.count}</em>
            </span>
          ))}
        </div>
      ) : null}
    </details>
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
