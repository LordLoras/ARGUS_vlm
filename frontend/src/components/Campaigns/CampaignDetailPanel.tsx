import { useState } from "react";

import { EditIcon, PlusIcon, TrashIcon, XIcon } from "../../lib/icons";
import type {
  CampaignAd,
  CampaignCount,
  CampaignDetail,
  CampaignInsight,
  CampaignResearch
} from "../../lib/types";

export function CampaignDetailPanel({
  detail,
  loading,
  onEdit,
  onDelete,
  onAssign,
  onUnassign,
  assigning,
  unassigningAdId
}: {
  detail?: CampaignDetail;
  loading?: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onAssign: (adIds: string[]) => void;
  onUnassign: (adId: string) => void;
  assigning?: boolean;
  unassigningAdId?: string | null;
}) {
  const [adIdsText, setAdIdsText] = useState("");

  if (loading) {
    return <div className="campaign-detail-shell obs-empty">Loading campaign detail...</div>;
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
      <header className="campaign-detail-head">
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

      {campaign.description ? <p className="campaign-description">{campaign.description}</p> : null}

      <div className="campaign-metrics">
        <Metric label="Ads" value={String(research.summary.ad_count)} sub={`${research.summary.user_assigned ?? 0} user / ${research.summary.auto_assigned ?? 0} auto`} />
        <Metric label="Mean sim" value={formatScore(research.summary.mean_similarity)} sub="cluster cohesion" />
        <Metric label="Confidence" value={formatScore(research.summary.avg_confidence)} sub={research.summary.min_confidence != null ? `min ${formatScore(research.summary.min_confidence)}` : "classification avg"} />
        <Metric label="Span" value={research.summary.span_days != null ? `${research.summary.span_days}d` : "-"} sub={formatRange(research.summary.first_seen, research.summary.last_seen)} />
      </div>

      <section className="campaign-section">
        <div className="section-title">Research brief</div>
        <InsightList insights={research.insights} />
      </section>

      <div className="campaign-research-grid">
        <section className="campaign-section">
          <div className="section-title">Messaging</div>
          <CountList title="Products" items={research.messaging.top_products} />
          <CountList title="Offers" items={research.messaging.top_offers} />
          <CountList title="CTAs" items={research.messaging.top_ctas} />
          <CountList title="Campaign language" items={research.messaging.campaign_signals} />
        </section>

        <section className="campaign-section">
          <div className="section-title">Market read</div>
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

      <section className="campaign-section">
        <div className="section-title">Analyst questions</div>
        <div className="prompt-list">
          {research.research_prompts.map((prompt) => (
            <span key={prompt}>{prompt}</span>
          ))}
        </div>
      </section>

      <section className="campaign-section">
        <div className="campaign-section-head">
          <div className="section-title">Assigned ads</div>
          <div className="campaign-ad-add">
            <input
              className="input mono"
              value={adIdsText}
              onChange={(event) => setAdIdsText(event.target.value)}
              placeholder="ad_id, ad_id"
            />
            <button className="btn btn-sm" onClick={submitAssignment} disabled={!adIdsText.trim() || assigning}>
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
    </section>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="campaign-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}

function InsightList({ insights }: { insights: CampaignInsight[] }) {
  if (!insights.length) {
    return <div className="obs-empty">No strong campaign-level patterns yet.</div>;
  }
  return (
    <div className="insight-list">
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

function formatScore(value?: number | null) {
  return value == null ? "-" : value.toFixed(2);
}

function formatRange(first?: string | null, last?: string | null) {
  const left = first ? first.slice(0, 10) : "";
  const right = last ? last.slice(0, 10) : "";
  if (left && right && left !== right) return `${left} - ${right}`;
  return left || right || "date range";
}

function emptyResearch(adCount: number): CampaignResearch {
  const emptyCounts: CampaignCount[] = [];
  return {
    summary: {
      ad_count: adCount,
      user_assigned: 0,
      auto_assigned: 0,
      mean_similarity: null,
      avg_confidence: null,
      min_confidence: null,
      first_seen: null,
      last_seen: null,
      span_days: null,
      brands: emptyCounts,
      advertisers: emptyCounts,
      categories: emptyCounts,
      subcategories: emptyCounts
    },
    messaging: {
      top_products: emptyCounts,
      top_offers: emptyCounts,
      top_ctas: emptyCounts,
      top_prices: emptyCounts,
      campaign_signals: emptyCounts
    },
    creative: {
      aspect_ratios: emptyCounts,
      formats: emptyCounts,
      voiceover_ads: 0,
      on_screen_text_ads: 0,
      disclaimer_ads: 0,
      small_print_ads: 0,
      disclaimer_density: emptyCounts
    },
    watchouts: {
      risk_labels: emptyCounts,
      disclaimer_count: 0,
      small_print_count: 0,
      low_confidence_ads: []
    },
    insights: [],
    research_prompts: []
  };
}
