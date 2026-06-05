import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  BadgeCheck,
  Bot,
  Database,
  FileSearch,
  GitBranch,
  Layers,
  ListChecks,
  Network,
  Radar,
  Route,
  ScanSearch,
  ShieldCheck,
  Workflow,
} from "lucide-react";

import bannerUrl from "../../banner.jpg";
import logoUrl from "../../logo-mark.png";

type CardItem = {
  title: string;
  body: string;
  icon: LucideIcon;
  color?: string;
};

type RouteItem = {
  label: string;
  to: string;
  note: string;
  icon: LucideIcon;
};

const WORKBENCH_CARDS: CardItem[] = [
  {
    title: "Product-level records",
    body: "Creates canonical product pages that can outlive a single ad, with aliases, evidence, related ads, taxonomy mappings, and editable review status.",
    icon: Layers,
    color: "var(--sky)",
  },
  {
    title: "Relationship graph",
    body: "Models products, brands, owners, categories, taxonomy nodes, and ad observations as typed relationships instead of loosely related text fields.",
    icon: Network,
    color: "var(--emerald)",
  },
  {
    title: "Evidence-aware automation",
    body: "Uses resolver, crawler, and VLM verification steps to improve entity quality while preserving provenance and candidate states for weak signals.",
    icon: Bot,
    color: "var(--amber)",
  },
];

const PRINCIPLE_CARDS: CardItem[] = [
  {
    title: "Separate experimental store",
    body: "The entity graph is maintained in a separate local database so new graph behavior can be tested without changing the core ad library by default.",
    icon: Database,
    color: "var(--sky)",
  },
  {
    title: "Grounded facts first",
    body: "Internal ad evidence, taxonomy records, crawler output, and model verification are stored with source context so later review can trace why a field exists.",
    icon: FileSearch,
    color: "var(--emerald)",
  },
  {
    title: "Candidate before confirmed",
    body: "Weak mentions, conflicting results, and web-only discoveries remain candidates until enough evidence or review supports promotion.",
    icon: ShieldCheck,
    color: "var(--rose)",
  },
  {
    title: "Strict taxonomy direction",
    body: "Future category decisions should prefer canonical IAB product and content taxonomy IDs, with free-text labels treated as hints until mapped.",
    icon: ListChecks,
    color: "var(--accent-2)",
  },
];

const ROUTE_LINKS: RouteItem[] = [
  {
    label: "Product Entities",
    to: "/experimental/products",
    note: "Canonical product pages and reviewable entity records.",
    icon: Layers,
  },
  {
    label: "Crawler Review",
    to: "/experimental/crawler",
    note: "Run crawl/VLM enrichment and review suggested ad-record changes.",
    icon: ScanSearch,
  },
  {
    label: "Brand Graph",
    to: "/experimental/brand-graph",
    note: "Inspect typed product, brand, owner, category, and ad relationships.",
    icon: Network,
  },
  {
    label: "Entity Resolver",
    to: "/experimental/entity-resolver",
    note: "Preview candidate creation, promotion, rejection, and resolver status.",
    icon: GitBranch,
  },
  {
    label: "Taxonomy Mapping",
    to: "/experimental/taxonomy-mapping",
    note: "Audit confidence-aware mappings across product and content taxonomy.",
    icon: Route,
  },
];

const ROADMAP = [
  ["Near term", "Improve target selection, crawler provenance, and VLM JSON verification so product and brand facts are cleaner before review."],
  ["Data quality", "Use suggested corrections to repair incorrect projected ad fields only after explicit approval, with an audit trail."],
  ["Taxonomy", "Align graph categories to IAB product and content taxonomy IDs, keeping free-text category names as unmapped hints."],
  ["Upload assist", "Offer an optional ingest mode that can keep initial metadata, use reviewed graph facts, or crawl again to reinforce weak fields."],
  ["Scale path", "Keep the SQLite graph schema portable so the same model can migrate to a dedicated graph database later if volume requires it."],
];

export function ExperimentalAbout() {
  return (
    <div className="about-page experimental-about-page">
      <section className="about-hero experimental-about-hero">
        <div className="about-hero-bg">
          <img src={bannerUrl} alt="" />
        </div>
        <div className="about-hero-pattern" />
        <div className="about-hero-inner">
          <div className="about-hero-copy">
            <div className="about-kicker">
              <span className="about-live-dot" />
              Experimental overview
            </div>
            <h1>Experimental Workbench</h1>
            <p className="about-hero-subtitle">
              A focused workspace for turning ad-level observations into durable product, brand,
              owner, category, and taxonomy records that can support higher-confidence analysis
              across future uploads.
            </p>
            <div className="about-hero-actions">
              <Link to="/experimental/products" className="about-btn about-btn-primary">
                <Layers size={15} />
                Open entities
              </Link>
              <Link to="/experimental/crawler" className="about-btn">
                <ScanSearch size={15} />
                Review crawler queue
              </Link>
              <Link to="/experimental/brand-graph" className="about-btn">
                <Network size={15} />
                View graph
              </Link>
            </div>
          </div>

          <div className="about-demo-panel experimental-about-panel" aria-label="Experimental graph overview">
            <div className="about-demo-topbar">
              <span className="about-window-dot" />
              <span className="about-window-dot" />
              <span className="about-window-dot" />
              <strong>entity_graph.db</strong>
            </div>
            <div className="experimental-about-map">
              {[
                ["Ads", "read-only input", "var(--sky)"],
                ["Products", "canonical nodes", "var(--emerald)"],
                ["Brands", "ownership links", "var(--amber)"],
                ["Taxonomy", "IAB mappings", "var(--accent-2)"],
              ].map(([label, note, color]) => (
                <div key={label} className="experimental-about-node" style={{ "--node-color": color } as CSSProperties}>
                  <strong>{label}</strong>
                  <span>{note}</span>
                </div>
              ))}
            </div>
            <div className="about-proof-strip experimental-about-proof">
              <div>
                <BadgeCheck size={16} />
                <span>Confirmed and candidate records are separated.</span>
              </div>
              <div>
                <Radar size={16} />
                <span>Crawler output is discovery evidence, not automatic truth.</span>
              </div>
              <div>
                <Workflow size={16} />
                <span>Future ingest can use graph confidence as an optional signal.</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="about-section">
        <div className="about-section-head">
          <span>01</span>
          <div>
            <h2>What The Experimental Tabs Achieve</h2>
            <p>These surfaces test a product-entity layer that is separate from the core ad library.</p>
          </div>
        </div>
        <div className="about-lead-block">
          <p>
            The experimental area explores how ARGUS can move from individual ad classifications
            toward a reusable entity graph. The goal is to make products and brands more accurate,
            auditable, and useful over time without treating every early signal as confirmed data.
          </p>
        </div>
        <CardGrid items={WORKBENCH_CARDS} />
      </section>

      <section className="about-section">
        <div className="about-section-head">
          <span>02</span>
          <div>
            <h2>Operating Principles</h2>
            <p>How the experimental layer should behave while the workflow is still evolving.</p>
          </div>
        </div>
        <CardGrid items={PRINCIPLE_CARDS} columns="two" />
      </section>

      <section className="about-section">
        <div className="about-section-head">
          <span>03</span>
          <div>
            <h2>Route Guide</h2>
            <p>Each tab focuses on one part of entity discovery, verification, or review.</p>
          </div>
        </div>
        <div className="about-feature-grid">
          {ROUTE_LINKS.map((feature) => {
            const Icon = feature.icon;
            return (
              <Link key={feature.label} to={feature.to} className="about-feature-link">
                <Icon size={18} />
                <strong>{feature.label}</strong>
                <span>{feature.note}</span>
                <ArrowRight size={15} />
              </Link>
            );
          })}
        </div>
      </section>

      <section className="about-section">
        <div className="about-section-head">
          <span>04</span>
          <div>
            <h2>Planned Direction</h2>
            <p>A practical roadmap for making the graph useful as a quality layer for future uploads.</p>
          </div>
        </div>
        <div className="about-stack-table">
          {ROADMAP.map(([label, detail]) => (
            <div key={label} className="about-stack-row">
              <strong>{label}</strong>
              <span>{detail}</span>
              <code>experimental graph</code>
            </div>
          ))}
        </div>
        <div className="about-plain-callout about-plain-callout-sky">
          <ShieldCheck size={18} />
          <span>
            The long-term intent is to let the product graph improve confidence during ingest:
            keep initial VLM metadata when appropriate, reuse reviewed graph facts when confidence
            is high, or crawl again when the system needs reinforcement.
          </span>
        </div>
      </section>

      <footer className="about-footer">
        <div className="about-footer-brand">
          <img src={logoUrl} alt="" />
          <div>
            <strong>ARGUS Experimental</strong>
            <span>Overview, product entities, brand graph, crawler review, and taxonomy mapping</span>
          </div>
        </div>
        <p>
          This area is a controlled workspace for product and brand graph development.
          Records are designed to remain traceable, reviewable, and portable as the
          entity layer matures.
        </p>
      </footer>
    </div>
  );
}

function CardGrid({ items, columns = "three" }: { items: CardItem[]; columns?: "two" | "three" }) {
  return (
    <div className={`about-card-grid about-card-grid-${columns}`}>
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <article
            key={item.title}
            className="about-info-card"
            style={{ "--card-color": item.color ?? "var(--accent-2)" } as CSSProperties}
          >
            <span className="about-card-mark">
              <Icon size={18} />
            </span>
            <strong>{item.title}</strong>
            <p>{item.body}</p>
          </article>
        );
      })}
    </div>
  );
}
