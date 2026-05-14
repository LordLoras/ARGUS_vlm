import { useState } from "react";

import { EditIcon, PlusIcon, TrashIcon, XIcon } from "../../lib/icons";
import type {
  CampaignAd,
  CampaignCount,
  CampaignDeepResearch,
  CampaignDetail,
  CampaignInsight,
  CampaignResearch
} from "../../lib/types";
import { CampaignAgentPanel } from "./CampaignAgentPanel";
import { buildSignalCards, emptyResearch, formatRange, formatScore } from "./campaignDetailUtils";

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
  const signals = buildSignalCards(research);

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
        <Metric label="Ads" value={String(research.summary.ad_count)} sub={`${research.summary.user_assigned ?? 0} user / ${research.summary.auto_assigned ?? 0} auto`} />
        <Metric label="Cohesion" value={formatScore(research.summary.mean_similarity)} sub="cluster score" />
        <Metric label="Confidence" value={formatScore(research.summary.avg_confidence)} sub={research.summary.min_confidence != null ? `min ${formatScore(research.summary.min_confidence)}` : "entity quality"} />
        <Metric label="Span" value={research.summary.span_days != null ? `${research.summary.span_days}d` : "-"} sub={formatRange(research.summary.first_seen, research.summary.last_seen)} />
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
          insights={research.insights.slice(0, 3)}
          signals={signals}
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
  insights,
  signals,
  description
}: {
  insights: CampaignInsight[];
  signals: Array<{ label: string; value: string; detail: string }>;
  description?: string | null;
}) {
  return (
    <div className="campaign-tab-pane">
      {description ? <p className="campaign-description compact">{description}</p> : null}
      <section className="campaign-section first">
        <div className="section-title">Executive read</div>
        <InsightList insights={insights} compact />
      </section>
      <section className="campaign-section">
        <div className="section-title">Key signals</div>
        <div className="campaign-signal-grid">
          {signals.map((signal) => (
            <div key={signal.label} className="campaign-signal">
              <span>{signal.label}</span>
              <strong>{signal.value}</strong>
              <small>{signal.detail}</small>
            </div>
          ))}
        </div>
      </section>
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
          <CountList title="Offers" items={research.messaging.top_offers} />
          <CountList title="CTAs" items={research.messaging.top_ctas} />
          <CountList title="Campaign language" items={research.messaging.campaign_signals} />
        </section>

        <section className="campaign-section first">
          <div className="section-title">Creative footprint</div>
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

function Metric({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="campaign-metric">
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
