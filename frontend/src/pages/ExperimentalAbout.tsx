import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  BadgeCheck,
  Bot,
  Camera,
  CheckCircle2,
  Database,
  FileSearch,
  GitBranch,
  Globe2,
  Layers,
  Link2,
  ListChecks,
  Network,
  Radar,
  Route,
  ScanSearch,
  ShieldCheck,
  ShieldAlert,
  Timer,
  TrendingUp,
  Webhook,
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
    body: "Uses resolver, background crawler runs, search, manual targets, rerun modes, and VLM verification to improve entity quality while preserving provenance and candidate states for weak signals.",
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
    body: "Internal ad evidence, taxonomy records, crawler output, search attempts, and model verification are stored with source context so later review can trace why a field exists.",
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
  {
    title: "Browser evidence as escalation",
    body: "Playwright-rendered pages and screenshots are escalation paths when HTTP text is thin, JavaScript hides product details, or anti-bot/4xx responses prevent useful evidence; blocked targets are flagged explicitly.",
    icon: Camera,
    color: "var(--amber)",
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
    note: "Start background crawler runs with skip, idempotent rerun, refresh, blocked-target, and official follow-up handling.",
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

const ROADMAP_CARDS: CardItem[] = [
  {
    title: "Scheduled re-crawls",
    body: "Automatically re-visit confirmed entities on a configurable cadence to detect stale product pages, discontinued products, or brand changes. Reruns are currently manual.",
    icon: Timer,
    color: "var(--rose)",
  },
  {
    title: "Crawl success metrics",
    body: "Dashboard stats tracking block rate, success rate, and average evidence per entity. Makes it possible to measure whether the anti-bot resolver and search API integrations are improving coverage.",
    icon: TrendingUp,
    color: "var(--sky)",
  },
  {
    title: "Structured search API",
    body: "Replace DuckDuckGo HTML scraping with a paid search API for stable, structured discovery results that bypass bot-detection layers entirely.",
    icon: Radar,
    color: "var(--sky)",
  },
  {
    title: "Anti-bot resolver",
    body: "Add a Cloudflare challenge resolver to recover blocked pages when standard HTTP and browser fallback both fail against 403, CAPTCHA, and WAF protections.",
    icon: ShieldAlert,
    color: "var(--rose)",
  },
  {
    title: "Deep crawls",
    body: "Extend the crawler beyond landing pages to follow internal product catalog links, category listings, and specification pages so that a single seed URL can surface multiple related entities.",
    icon: Webhook,
    color: "var(--sky)",
  },
  {
    title: "Chain search",
    body: "When a crawl or VLM pass identifies a distinct product or brand with high confidence, automatically queue it as a new crawl target and insert the resulting entity into the graph without manual review.",
    icon: Link2,
    color: "var(--accent-2)",
  },
  {
    title: "Search targets",
    body: "Continue improving generated brand-product and brand-only search queries while exposing query metadata, parsed result URLs, and manual official-target overrides.",
    icon: Globe2,
    color: "var(--sky)",
  },
  {
    title: "Evidence quality",
    body: "Improve target selection, blocked-page detection, official-page follow-ups, and VLM verification so product and brand facts are cleaner before review.",
    icon: FileSearch,
    color: "var(--amber)",
  },
  {
    title: "Data quality",
    body: "Use suggested corrections to repair incorrect projected ad fields only after explicit approval, with an audit trail.",
    icon: BadgeCheck,
    color: "var(--emerald)",
  },
  {
    title: "Taxonomy alignment",
    body: "Significant improvement needed to align graph categories to IAB product and content taxonomy IDs. Free-text category names are currently treated as unmapped hints and require systematic mapping and review.",
    icon: ListChecks,
    color: "var(--rose)",
  },
  {
    title: "Upload assist",
    body: "Offer an optional ingest mode that can keep initial metadata, use reviewed graph facts, or crawl again to reinforce weak fields.",
    icon: Layers,
    color: "var(--sky)",
  },
  {
    title: "Scale path",
    body: "Keep the SQLite graph schema portable so the same model can migrate to a dedicated graph database later if volume requires it.",
    icon: Database,
    color: "var(--amber)",
  },
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
              owner, category, and taxonomy records. Submitted URLs, manual reference targets, and
              search-backed discovery feed a separate entity graph without modifying core ad records.
              Crawler runs persist as background jobs with skip, idempotent rerun, and refresh modes,
              and Playwright rendering handles pages that need JavaScript or screenshot verification.
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
                <span>Search and crawler output are discovery evidence, not automatic truth.</span>
              </div>
              <div>
                <Globe2 size={16} />
                <span>No-URL ads and carrier offers can trigger generated queries, parsed results, and official manufacturer follow-ups.</span>
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
            The experimental area moves ARGUS from individual ad classifications toward a reusable
            entity graph. Products and brands are tracked as durable, auditable records rather than
            treating every early signal as confirmed data. The crawler resolves missing targets
            through submitted URLs, user-provided official URLs, or generated brand and product
            search queries. Crawl runs persist in the background with support for skipping completed
            ads, idempotent reruns, and selective artifact refresh. Playwright browser escalation
            and screenshot-to-VLM verification handle pages where static fetches are insufficient.
            Current focus is on expanding coverage through structured search APIs, anti-bot
            resolvers, and deeper crawl strategies.
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
        <CardGrid items={ROADMAP_CARDS} columns="two" />
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
