import { useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { Link } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  BadgeInfo,
  BarChart3,
  BrainCircuit,
  Clock3,
  Database,
  Eye,
  FileSearch,
  GitBranch,
  Layers,
  ListTree,
  LockKeyhole,
  MessageSquare,
  Network,
  Play,
  Radar,
  ScanLine,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Tags,
  Upload,
  Workflow,
  Zap,
} from "lucide-react";

import bannerUrl from "../../banner.jpg";
import logoUrl from "../../logo-mark.png";
import benchmarkData from "../data/modelBenchmarkResults.json";

type DemoStep = {
  label: string;
  title: string;
  plain: string;
  tech: string;
  icon: LucideIcon;
  color: string;
};

type CardItem = {
  title: string;
  body: string;
  icon: LucideIcon;
  color?: string;
};

type BenchmarkSummaryModel = {
  name: string;
  route_type: string;
  score: number;
  completion_seconds: number;
  successful_ads: number;
  total_ads: number;
};

type BenchmarkSummaryPayload = {
  benchmark_date_label: string;
  models: BenchmarkSummaryModel[];
};

const benchmarkSummary = benchmarkData as BenchmarkSummaryPayload;

const DEMO_STEPS: DemoStep[] = [
  {
    label: "Upload",
    title: "A video becomes a tracked job",
    plain: "Drop in a TV spot or promo video. ARGUS extracts frames, audio, hashes, and progress events locally.",
    tech: "ffmpeg, SHA256, restartable artifacts, SSE",
    icon: Upload,
    color: "var(--sky)",
  },
  {
    label: "Read",
    title: "The system collects evidence",
    plain: "It reads on-screen text, listens to voiceover, keeps timestamps, and preserves raw extraction output.",
    tech: "PaddleOCR, PaddleOCR-VL (conditional), Whisper",
    icon: ScanLine,
    color: "var(--emerald)",
  },
  {
    label: "Understand",
    title: "Models verify, not guess alone",
    plain: "Rules and a vision-language model combine the evidence into categories, offers, CTAs, disclaimers, and confidence.",
    tech: "rules, VLM verifier, marketing entities",
    icon: BrainCircuit,
    color: "var(--amber)",
  },
  {
    label: "Index",
    title: "Every ad becomes searchable",
    plain: "The record is saved with full text search, text vectors, visual frame vectors, and related-ad signals.",
    tech: "SQLite WAL, FTS5, MiniLM, SigLIP 2, sqlite-vec",
    icon: Database,
    color: "var(--rose)",
  },
  {
    label: "Ask",
    title: "Analysts can ask questions",
    plain: "The agent answers through read-only tools, cites real ad and campaign IDs, and leaves an audit trail.",
    tech: "tool calls, query_only SQLite, audited sessions",
    icon: MessageSquare,
    color: "var(--accent-2)",
  },
];

const PROBLEM_CARDS: CardItem[] = [
  {
    title: "Ads are messy video, not neat rows",
    body: "Important claims can appear for half a second, in a voiceover, in an end card, or in fine print.",
    icon: Play,
    color: "var(--sky)",
  },
  {
    title: "Marketing details need structure",
    body: "Brand, product, price, offer, CTA, social proof, and disclaimers are extracted into reusable fields.",
    icon: Tags,
    color: "var(--amber)",
  },
  {
    title: "Campaigns repeat with small changes",
    body: "ARGUS detects exact duplicates, near creative reuse, and semantic variants across a campaign.",
    icon: GitBranch,
    color: "var(--emerald)",
  },
];

const SCOPE_CARDS: CardItem[] = [
  {
    title: "Ad evidence workspace",
    body: "Supports creative inspection, campaign comparison, claim mining, and evidence retrieval from a growing ad database.",
    icon: Radar,
    color: "var(--sky)",
  },
  {
    title: "Works from video evidence",
    body: "Ingest MP4, MOV, or WebM clips. The pipeline samples frames, aligns transcript segments, preserves OCR, and records timestamps.",
    icon: Play,
    color: "var(--emerald)",
  },
  {
    title: "Structured taxonomy output",
    body: "Records category labels, observation tags, confidence, evidence timestamps, and marketing entities in one classification record.",
    icon: ShieldCheck,
    color: "var(--amber)",
  },
  {
    title: "Designed for traceable answers",
    body: "When a model extracts a brand, price, offer, CTA, claim, or disclaimer, the value is expected to point back to frame or transcript evidence.",
    icon: FileSearch,
    color: "var(--rose)",
  },
];

const TRUST_CARDS: CardItem[] = [
  {
    title: "Evidence before opinion",
    body: "Final outputs cite frames, timestamps, OCR text, transcript segments, rules, or model evidence.",
    icon: FileSearch,
    color: "var(--sky)",
  },
  {
    title: "Configurable runtime",
    body: "SQLite stores the working dataset, while OCR, VLM, embedding, and agent routes are configured through the backend and Settings UI.",
    icon: Server,
    color: "var(--emerald)",
  },
  {
    title: "Agent cannot mutate data",
    body: "The natural-language agent routes to fixed read-only tools and uses SQLite query_only enforcement.",
    icon: LockKeyhole,
    color: "var(--rose)",
  },
];

const OUTPUT_CARDS: CardItem[] = [
  {
    title: "Primary category",
    body: "Every ad receives a primary category from the ARGUS taxonomy, with separate IAB product and content projections when those mappings are available.",
    icon: ListTree,
    color: "var(--sky)",
  },
  {
    title: "Observation tags",
    body: "Descriptive labels like urgency pressure, deceptive imagery, health claims, and unsubstantiated claims. They surface in search and filtering, but never block or escalate.",
    icon: Tags,
    color: "var(--amber)",
  },
  {
    title: "Marketing entities",
    body: "Structured extraction of brand, products, prices, offers, CTAs, social proof, and disclaimers — each grounded to a specific frame or transcript segment with timestamps.",
    icon: FileSearch,
    color: "var(--emerald)",
  },
  {
    title: "Evidence chain",
    body: "Every classification result cites its sources: which frame, which OCR line, which transcript segment, which rule triggered. Raw and corrected OCR are stored separately.",
    icon: Clock3,
    color: "var(--rose)",
  },
  {
    title: "Brand enrichment",
    body: "Enrich any brand or advertiser with a Wikipedia and Wikidata profile on demand — logo, description, industry, and linked entities. Additional search integrations can be added later.",
    icon: BadgeInfo,
    color: "var(--accent-2)",
  },
];

const SEARCH_CARDS: CardItem[] = [
  {
    title: "Keyword",
    body: "Exact brands, products, phone numbers, prices, and phrases.",
    icon: Search,
    color: "var(--sky)",
  },
  {
    title: "Semantic text",
    body: "Meaning-based matches when the exact words are different.",
    icon: BrainCircuit,
    color: "var(--accent-2)",
  },
  {
    title: "Visual",
    body: "Find frames by what appears on screen: cars, doctors, podiums, app screens, fine print.",
    icon: Eye,
    color: "var(--emerald)",
  },
  {
    title: "Hybrid",
    body: "Combines exact terms and embeddings, then fuses ranks for analyst search.",
    icon: Network,
    color: "var(--amber)",
  },
  {
    title: "Campaigns",
    body: "Group related creative, compare variants, and preserve user-curated assignments.",
    icon: GitBranch,
    color: "var(--rose)",
  },
];

const FEATURE_CARDS: CardItem[] = [
  {
    title: "Natural-Language Agent",
    body: "Ask questions in plain English. The agent calls read-only tools, cites ad and campaign IDs, and logs every turn.",
    icon: MessageSquare,
    color: "var(--accent-2)",
  },
  {
    title: "Creative Debate Panel",
    body: "Adversarial persona debate with opening statements, cross-examination, closing arguments, tensions, and a moderator scorecard.",
    icon: BrainCircuit,
    color: "var(--amber)",
  },
  {
    title: "Knowledge Graph",
    body: "Interactive graph visualization of entity relationships across the ad library. Select a node to trace brand, product, and category connections. Designed to expand with agentic auto-discovery of emerging signals and cross-campaign patterns.",
    icon: Network,
    color: "var(--emerald)",
  },
  {
    title: "Embedding Space",
    body: "Interactive UMAP projection of text and visual vectors. Explore ad similarity, clusters, and outliers by dragging through embedding space. Projections reflect neighborhood structure, not exact distances.",
    icon: Radar,
    color: "var(--rose)",
  },
];

const STACK_LAYERS = [
  {
    layer: "Interface",
    plain: "React app for upload, library, search, campaigns, graph, and agent chat.",
    tech: "Vite + React + TypeScript",
  },
  {
    layer: "API",
    plain: "A decoupled service surface for JSON requests and live progress streams.",
    tech: "FastAPI + OpenAPI + SSE",
  },
  {
    layer: "Worker",
    plain: "A restartable pipeline that caches each stage so failed work can resume.",
    tech: "Python stages + local artifacts",
  },
  {
    layer: "Evidence store",
    plain: "One local database stores ads, frames, OCR, transcripts, classifications, and agent audits.",
    tech: "SQLite WAL + FTS5 + sqlite-vec",
  },
  {
    layer: "Models",
    plain: "Specialized models read text, listen to audio, verify visuals, and create embeddings.",
    tech: "PaddleOCR, Whisper, Gemma/VLM, MiniLM, SigLIP 2",
  },
];

const QUESTION_EXAMPLES = [
  "Which ads use urgency language?",
  "Show automotive ads with small disclaimers.",
  "Find variants of this campaign with a different offer.",
  "Which brands mention ratings or testimonials?",
  "Find ads that visually show a mobile app screen.",
  "What claims does this ad make, and where are they shown?",
];

const FEATURE_LINKS = [
  { label: "Upload", to: "/upload", icon: Upload, note: "start the pipeline" },
  { label: "Library", to: "/library", icon: Layers, note: "inspect records" },
  { label: "Search", to: "/search", icon: Search, note: "retrieve ads" },
  { label: "Campaigns", to: "/campaigns", icon: GitBranch, note: "group variants" },
  { label: "Agent", to: "/agent", icon: MessageSquare, note: "ask questions" },
  { label: "Embeddings", to: "/embeddings", icon: Radar, note: "show vector space" },
];

const EXPERIMENTAL_LINKS = [
  { label: "Product Entities", to: "/experimental/products", icon: Layers, note: "canonical product pages" },
  { label: "Brand Graph", to: "/experimental/brand-graph", icon: Network, note: "brand and owner links" },
  { label: "Entity Resolver", to: "/experimental/entity-resolver", icon: FileSearch, note: "candidate promotion" },
  { label: "Taxonomy Mapping", to: "/experimental/taxonomy-mapping", icon: ListTree, note: "confidence-aware mappings" },
];

function FadeSection({
  children,
  className,
  id,
}: {
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setVisible(true);
        observer.disconnect();
      },
      { threshold: 0.12 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section
      ref={ref}
      id={id}
      className={className}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "translateY(0)" : "translateY(24px)",
        transition:
          "opacity 650ms cubic-bezier(0.16,1,0.3,1), transform 650ms cubic-bezier(0.16,1,0.3,1)",
      }}
    >
      {children}
    </section>
  );
}

function DemoSignalPanel({ activeStep }: { activeStep: number }) {
  const active = DEMO_STEPS[activeStep];
  const ActiveIcon = active.icon;
  const panelStyle = { "--demo-accent": active.color } as CSSProperties;

  return (
    <div className="about-demo-panel" style={panelStyle} aria-label="Animated ARGUS pipeline preview">
      <div className="about-demo-topbar">
        <span className="about-window-dot" />
        <span className="about-window-dot" />
        <span className="about-window-dot" />
        <strong>pipeline.argus</strong>
      </div>

      <div className="about-demo-grid">
        <div className="about-demo-video">
          <div className="about-demo-frame about-demo-frame-a">
            <span>00:04.5</span>
            <strong>LIMITED TIME</strong>
            <em>$299/mo</em>
            <i className="about-scan-line" />
          </div>
          <div className="about-demo-frame about-demo-frame-b">
            <span>00:11.0</span>
            <strong>Brand logo</strong>
            <em>CTA detected</em>
          </div>
          <div className="about-demo-frame about-demo-frame-c">
            <span>00:23.5</span>
            <strong>Fine print</strong>
            <em>OCR check</em>
          </div>
        </div>

        <div className="about-demo-current">
          <div className="about-demo-current-icon">
            <ActiveIcon size={22} />
          </div>
          <span>Current talking point</span>
          <strong>{active.title}</strong>
          <p>{active.plain}</p>
          <code>{active.tech}</code>
        </div>

        <div className="about-demo-agent">
          <div className="about-agent-prompt">Ask: ads using urgency + price offers</div>
          <div className="about-agent-answer">
            <Sparkles size={14} />
            <span>Found 12 ads. Top evidence: timestamps, OCR snippets, campaign variants.</span>
          </div>
          <div className="about-agent-bars">
            <i style={{ width: "84%" }} />
            <i style={{ width: "62%" }} />
            <i style={{ width: "72%" }} />
          </div>
        </div>
      </div>

      <div className="about-demo-rail">
        {DEMO_STEPS.map((step, index) => {
          const Icon = step.icon;
          return (
            <div
              key={step.label}
              className="about-demo-rail-node"
              data-active={index === activeStep}
              style={{ "--node-color": step.color } as CSSProperties}
            >
              <Icon size={15} />
              <span>{step.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StoryRail({
  activeStep,
  onActiveStep,
}: {
  activeStep: number;
  onActiveStep: (index: number) => void;
}) {
  return (
    <div className="about-story-rail">
      {DEMO_STEPS.map((step, index) => {
        const Icon = step.icon;
        return (
          <button
            key={step.label}
            type="button"
            className="about-story-step"
            data-active={activeStep === index}
            onFocus={() => onActiveStep(index)}
            onMouseEnter={() => onActiveStep(index)}
            onClick={() => onActiveStep(index)}
            style={{ "--step-color": step.color } as CSSProperties}
          >
            <span className="about-story-step-index">{String(index + 1).padStart(2, "0")}</span>
            <Icon className="about-story-step-icon" size={18} />
            <span className="about-story-step-copy">
              <strong>{step.label}</strong>
              <em>{step.plain}</em>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function CardGrid({ items, columns = "three" }: { items: CardItem[]; columns?: "two" | "three" | "five" }) {
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

export function About() {
  const [activeStep, setActiveStep] = useState(0);
  const [paused, setPaused] = useState(false);
  const measuredModels = benchmarkSummary.models.filter(
    (model) => model.total_ads > 0 && model.successful_ads === model.total_ads
  );
  const benchmarkLeader = measuredModels[0];
  const paidBenchmarkModels = measuredModels.filter((model) => model.route_type === "OpenRouter");
  const fastestPaidModel = paidBenchmarkModels.length
    ? paidBenchmarkModels.reduce((best, model) =>
        model.completion_seconds < best.completion_seconds ? model : best
      )
    : undefined;

  useEffect(() => {
    if (paused) return;
    const timer = window.setInterval(() => {
      setActiveStep((current) => (current + 1) % DEMO_STEPS.length);
    }, 2600);
    return () => window.clearInterval(timer);
  }, [paused]);

  const active = DEMO_STEPS[activeStep];
  const ActiveIcon = active.icon;

  return (
    <div className="about-page">
      <section className="about-hero">
        <div className="about-hero-bg">
          <img src={bannerUrl} alt="" />
        </div>
        <div className="about-hero-pattern" />
        <div className="about-hero-inner">
          <div className="about-hero-copy">
            <div className="about-kicker">
              <span className="about-live-dot" />
              Ad Retrieval, Graphing &amp; Understanding System
            </div>
            <h1>ARGUS</h1>
            <p className="about-hero-subtitle">
              A multimodal system that turns video ads into searchable evidence:
              categories, marketing entities, campaign variants, visual matches,
              and source-traceable agent answers.
            </p>
            {benchmarkLeader ? (
              <Link to="/benchmark" className="about-benchmark-callout">
                <span className="about-benchmark-mark">
                  <BarChart3 size={17} />
                  Model benchmark
                </span>
                <strong>{measuredModels.length} measured routes on five ad artifacts</strong>
                <em>
                  Leader: {benchmarkLeader.name} at {benchmarkLeader.score.toFixed(1)} / 100
                  {fastestPaidModel ? `; fastest paid route: ${fastestPaidModel.name} in ${formatAboutSeconds(fastestPaidModel.completion_seconds)}.` : "."}
                </em>
                <ArrowRight size={16} />
              </Link>
            ) : null}
            <div className="about-hero-actions">
              <a href="#demo-path" className="about-btn about-btn-primary">
                <Play size={15} />
                See the pipeline
              </a>
              <Link to="/upload" className="about-btn">
                <Upload size={15} />
                Upload an ad
              </Link>
              <Link to="/agent" className="about-btn">
                <MessageSquare size={15} />
                Ask the agent
              </Link>
              <Link to="/experimental/products" className="about-btn about-btn-experimental">
                <Sparkles size={15} />
                Experimental products
              </Link>
            </div>
          </div>

          <DemoSignalPanel activeStep={activeStep} />
        </div>
      </section>

      <FadeSection className="about-section about-section-experimental" id="experimental-products">
        <div className="about-experimental-callout">
          <div className="about-experimental-copy">
            <span className="about-mini-label">Post-submission experimental feature</span>
            <h2>Product entity graph work is visible here, but isolated on the experimental branch.</h2>
            <p>
              These routes run on the same local FastAPI/Vite server for convenience, while the new work lives on
              the <code>experimental</code> Git branch and writes only to the separate <code>entity_graph.db</code>.
              The submitted demo database is read through a read-only adapter.
            </p>
          </div>
          <div className="about-experimental-routes">
            {EXPERIMENTAL_LINKS.map((feature) => {
              const Icon = feature.icon;
              return (
                <Link key={feature.label} to={feature.to} className="about-experimental-route">
                  <Icon size={18} />
                  <strong>{feature.label}</strong>
                  <span>{feature.note}</span>
                  <ArrowRight size={15} />
                </Link>
              );
            })}
          </div>
        </div>
      </FadeSection>

      <FadeSection className="about-section about-section-intro" id="one-liner">
        <div className="about-section-head">
          <span>01</span>
          <div>
            <h2>What ARGUS Does</h2>
            <p>How the system processes video ads into structured, searchable records.</p>
          </div>
        </div>
        <div className="about-lead-block">
          <p>
            ARGUS watches an ad the way an analyst would: it sees the frames, reads
            visible text, listens to speech, notes the offer, checks for repeated
            campaign patterns, and stores everything as searchable evidence.
          </p>
        </div>
        <CardGrid items={PROBLEM_CARDS} />
      </FadeSection>

      <FadeSection className="about-section" id="scope">
        <div className="about-section-head">
          <span>02</span>
          <div>
            <h2>Scope And Inputs</h2>
            <p>What the system ingests, preserves, and exposes for analysis.</p>
          </div>
        </div>
        <CardGrid items={SCOPE_CARDS} columns="two" />
      </FadeSection>

      <FadeSection className="about-section" id="demo-path">
        <div className="about-section-head">
          <span>03</span>
          <div>
            <h2>How It Works</h2>
            <p>The pipeline stages that turn raw video into structured evidence.</p>
          </div>
        </div>
        <div className="about-demo-story"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
        >
          <StoryRail activeStep={activeStep} onActiveStep={setActiveStep} />
          <div className="about-story-focus" style={{ "--focus-color": active.color } as CSSProperties}>
            <span className="about-story-focus-icon">
              <ActiveIcon size={22} />
            </span>
            <div>
              <span className="about-mini-label">Say this</span>
              <h3>{active.title}</h3>
              <p>{active.plain}</p>
              <code>{active.tech}</code>
            </div>
          </div>
        </div>
      </FadeSection>

      <FadeSection className="about-section" id="pipeline">
        <div className="about-section-head">
          <span>04</span>
          <div>
            <h2>From Footage To Evidence</h2>
            <p>The pipeline is modular, restartable, and built around traceability.</p>
          </div>
        </div>
        <div className="about-flowline">
          {[
            ["Video", "upload + hash"],
            ["Frames", "sampled timeline"],
            ["Text", "OCR + transcript"],
            ["Evidence", "rules + bundle"],
            ["Verifier", "category + entities"],
            ["Index", "keyword + vectors"],
            ["Answer", "search + agent"],
          ].map(([title, detail], index) => (
            <div key={title} className="about-flowline-step" style={{ "--delay": `${index * 110}ms` } as CSSProperties}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{title}</strong>
              <em>{detail}</em>
            </div>
          ))}
        </div>
        <div className="about-proof-strip">
          <div>
            <Clock3 size={16} />
            <span>Every extracted claim keeps a timestamp.</span>
          </div>
          <div>
            <ShieldCheck size={16} />
            <span>Raw OCR is preserved separately from corrections.</span>
          </div>
          <div>
            <Workflow size={16} />
            <span>Completed stages are reused unless the job is forced.</span>
          </div>
        </div>
      </FadeSection>

      <FadeSection className="about-section" id="output">
        <div className="about-section-head">
          <span>05</span>
          <div>
            <h2>What Gets Generated</h2>
            <p>Every ad produces a structured record with an ARGUS category, optional IAB projections, observation tags, and marketing entities grounded to evidence.</p>
          </div>
        </div>
        <CardGrid items={OUTPUT_CARDS} columns="three" />
        <div className="about-stack-table" style={{ marginTop: 16 }}>
          {[
            ["Category", "primary_category + confidence", "e.g. automotive, healthcare_pharma, gambling"],
            ["IAB projections", "product and content taxonomy mappings when available", "e.g. Vehicles > Automotive Leasing"],
            ["Observation tags", "descriptive tags from rules and verifier output", "e.g. urgency_pressure, deceptive_imagery, health_claim"],
            ["Marketing entities", "brand, products, prices, offers, CTAs, social proof, disclaimers", "each grounded to frame index + time_ms"],
            ["Brand profile", "on-demand Wikipedia + Wikidata enrichment for brand/advertiser", "logo, description, industry, wikidata"],
            ["Campaigns", "auto-clustered or user-curated groups", "same brand, variants, different SKUs"],
            ["Embeddings", "384-d text + 768-d visual per keyframe", "MiniLM + SigLIP 2, stored in sqlite-vec"],
          ].map(([label, detail, example]) => (
            <div key={label} className="about-stack-row">
              <strong>{label}</strong>
              <span>{detail}</span>
              <code>{example}</code>
            </div>
          ))}
        </div>
      </FadeSection>

      <FadeSection className="about-section" id="questions">
        <div className="about-section-head">
          <span>06</span>
          <div>
            <h2>Ask In Plain Language</h2>
            <p>The agent answers natural-language queries over the full ad database.</p>
          </div>
        </div>
        <div className="about-question-cloud">
          {QUESTION_EXAMPLES.map((question, index) => (
            <span key={question} style={{ "--delay": `${index * 80}ms` } as CSSProperties}>
              {question}
            </span>
          ))}
        </div>
      </FadeSection>

      <FadeSection className="about-section" id="search">
        <div className="about-section-head">
          <span>07</span>
          <div>
            <h2>Search And Retrieval</h2>
            <p>Different retrieval modes answer different analyst questions.</p>
          </div>
        </div>
        <CardGrid items={SEARCH_CARDS} columns="five" />
        <div className="about-plain-callout about-plain-callout-sky">
          <Zap size={18} />
          <span>
            Hybrid search fuses keyword precision with semantic understanding using
            reciprocal rank fusion — combining exact matches with meaning-based
            retrieval so analysts find what they need regardless of phrasing.
            As the database grows, a custom reranker model will further tighten
            relevance and suppress weak partial matches.
          </span>
        </div>
      </FadeSection>

      <FadeSection className="about-section" id="features">
        <div className="about-section-head">
          <span>08</span>
          <div>
            <h2>Built-In Tools</h2>
            <p>Analysis surfaces beyond the core pipeline.</p>
          </div>
        </div>
        <CardGrid items={FEATURE_CARDS} columns="two" />
      </FadeSection>

      <FadeSection className="about-section" id="trust">
        <div className="about-section-head">
          <span>09</span>
          <div>
            <h2>Trust Boundaries</h2>
            <p>These points keep the project understandable and defensible.</p>
          </div>
        </div>
        <CardGrid items={TRUST_CARDS} columns="two" />
      </FadeSection>

      <FadeSection className="about-section" id="architecture">
        <div className="about-section-head">
          <span>10</span>
          <div>
            <h2>Under The Hood</h2>
            <p>A concise summary of the stack layers.</p>
          </div>
        </div>
        <div className="about-stack-table">
          {STACK_LAYERS.map((layer) => (
            <div key={layer.layer} className="about-stack-row">
              <strong>{layer.layer}</strong>
              <span>{layer.plain}</span>
              <code>{layer.tech}</code>
            </div>
          ))}
        </div>
        <div className="about-architecture-card">
          <div>
            <span className="about-mini-label">Backend contract</span>
            <p>
              The backend is the product core: API, worker, database, models, and agent tools.
              The frontend is a separate client over HTTP and SSE, so the system is not tied
              to one UI.
            </p>
          </div>
          <ArrowRight size={22} />
          <div>
            <span className="about-mini-label">Output contract</span>
            <p>
              Each final result includes category, confidence, observation tags,
              timestamped evidence, marketing entities, campaigns, embeddings, and
              related ads.
            </p>
          </div>
        </div>
      </FadeSection>

      <FadeSection className="about-section" id="tour">
        <div className="about-section-head">
          <span>11</span>
          <div>
            <h2>Explore</h2>
            <p>Navigate to any section of the application.</p>
          </div>
        </div>
        <div className="about-feature-grid">
          {FEATURE_LINKS.map((feature) => {
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
        <div className="about-explore-subsection">
          <div>
            <span className="about-mini-label">Experimental</span>
            <p>Post-submission routes for product entities, graph relations, resolver review, and taxonomy mapping.</p>
          </div>
          <div className="about-feature-grid about-feature-grid-experimental">
            {EXPERIMENTAL_LINKS.map((feature) => {
              const Icon = feature.icon;
              return (
                <Link key={feature.label} to={feature.to} className="about-feature-link about-feature-link-experimental">
                  <Icon size={18} />
                  <strong>{feature.label}</strong>
                  <span>{feature.note}</span>
                  <ArrowRight size={15} />
                </Link>
              );
            })}
          </div>
        </div>
      </FadeSection>

      <footer className="about-footer">
        <div className="about-footer-brand">
          <img src={logoUrl} alt="" />
          <div>
            <strong>ARGUS</strong>
            <span>Ad Retrieval, Graphing &amp; Understanding System</span>
          </div>
        </div>
        <p>
          Upload a video ad, let the pipeline build evidence, then search, compare,
          cluster, and ask questions — every answer traces back to the original
          frames.
        </p>
      </footer>
    </div>
  );
}

function formatAboutSeconds(seconds: number) {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}
