import { useMemo, useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import logoUrl from "../../logo-mark.png";
import bannerUrl from "../../banner.png";
import {
  LibraryIcon,
  UploadIcon,
  SearchIcon,
  CampaignsIcon,
  ChatIcon,
  FlowIcon,
  LayersIcon,
  SettingsIcon,
} from "../lib/icons";

/* Tiny animated counter. */
function CountUp({ target, suffix = "" }: { target: number; suffix?: string }) {
  const [val, setVal] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !started.current) {
          started.current = true;
          const duration = 1400;
          const start = performance.now();
          const tick = (now: number) => {
            const t = Math.min((now - start) / duration, 1);
            const ease = 1 - Math.pow(1 - t, 3);
            setVal(Math.round(ease * target));
            if (t < 1) requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
        }
      },
      { threshold: 0.3 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [target]);

  return (
    <span ref={ref}>
      {val.toLocaleString()}
      {suffix}
    </span>
  );
}

/* Section observer for fade-in. */
function FadeSection({
  children,
  className,
  id,
}: {
  children: React.ReactNode;
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
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.08 }
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
        transition: "opacity 0.6s cubic-bezier(0.16,1,0.3,1), transform 0.6s cubic-bezier(0.16,1,0.3,1)",
      }}
    >
      {children}
    </section>
  );
}

/* Pipeline stage visual. */
const PIPELINE_STAGES = [
  { num: "01", title: "Upload & Job Creation", desc: "Video ingest, SHA256 hash, job queueing, SSE progress streaming.", color: "var(--sky)" },
  { num: "02", title: "Frame & Audio Extraction", desc: "ffmpeg probing, frame sampling at configurable intervals, mono 16 kHz audio.", color: "var(--sky)" },
  { num: "03", title: "Frame Preprocessing", desc: "Blankness, blur, perceptual hash, near-duplicate removal, scene change detection.", color: "var(--accent-2)" },
  { num: "04", title: "OCR & Document OCR", desc: "PaddleOCR for grounded text, optional GLM-OCR for dense frames and fine print.", color: "var(--accent-2)" },
  { num: "05", title: "Transcript & Rules", desc: "Whisper transcription, frame alignment, deterministic rule triggers.", color: "var(--emerald)" },
  { num: "06", title: "Evidence Bundle", desc: "Deterministic frame selection: first/last, rule-trigger, OCR-dense, time-distributed.", color: "var(--emerald)" },
  { num: "07", title: "VLM Verification", desc: "Vision-language model classification, marketing entity extraction, confidence scoring.", color: "var(--amber)" },
  { num: "08", title: "Post-Processing", desc: "OCR cleanup, self-correction, visual verification, evidence aggregation.", color: "var(--amber)" },
  { num: "09", title: "Embeddings & Indexing", desc: "MiniLM text vectors, SigLIP 2 per-frame + ad-level visual vectors, FTS5 + sqlite-vec.", color: "var(--rose)" },
  { num: "10", title: "Campaigns & Agent", desc: "Semantic related ads, campaign discovery, read-only natural-language agent.", color: "var(--rose)" },
];

/* Search modes. */
const SEARCH_MODES = [
  { mode: "Keyword", signal: "FTS5", best: "Brands, offers, phone numbers, exact terms" },
  { mode: "Text Vector", signal: "MiniLM cosine", best: "Semantic text similarity across ads" },
  { mode: "Visual", signal: "SigLIP text-to-image", best: "Objects, scenes, people, layouts, frame-level matches" },
  { mode: "Hybrid", signal: "FTS + MiniLM + RRF", best: "General analyst search, terms and meaning both matter" },
  { mode: "Visual Hybrid", signal: "Keyword + SigLIP", best: "Specific visual queries with OCR/entity grounding" },
];

/* Dedup layers. */
const DEDUP_LAYERS = [
  { layer: "Exact File Hash", signal: "SHA256 bytes", purpose: "Identical upload detection" },
  { layer: "Near Creative Hash", signal: "Mean perceptual hash", purpose: "Visually near-identical creative" },
  { layer: "Post-OCR Duplicate", signal: "Frame pHash + OCR + transcript + offer signature", purpose: "Re-encoded exact same creative" },
  { layer: "Semantic Related", signal: "Text + visual vectors", purpose: "Same campaign, variant, or related creative" },
];

/* Model responsibilities. */
const MODELS = [
  { name: "PaddleOCR", role: "Raw visible text, boxes, confidence", grounding: "Preserved exactly as extracted" },
  { name: "GLM-OCR", role: "Hard-frame text parser for dense layouts", grounding: "Stored separately; advisory unless corroborated" },
  { name: "Whisper", role: "Transcript segments from extracted audio", grounding: "Aligned to frames, retained as full evidence" },
  { name: "Rules Engine", role: "Deterministic category and observation triggers", grounding: "Audit-friendly, never gating" },
  { name: "VLM Verifier", role: "Classification, OCR review, marketing entities", grounding: "Must cite evidence by timestamp" },
  { name: "MiniLM-L6-v2", role: "Ad-level text embeddings", grounding: "Transcript + searchable OCR text" },
  { name: "SigLIP 2", role: "Frame + ad-level visual embeddings", grounding: "Text-to-image visual queries" },
  { name: "Agent LLM", role: "Tool routing, campaign research, answers", grounding: "Read-only tools, no fabricated IDs" },
];

/* Nav features. */
const FEATURES = [
  { icon: LibraryIcon, title: "Library", to: "/library", desc: "Browse, filter, and manage classified ads with full evidence trails." },
  { icon: UploadIcon, title: "Upload", to: "/upload", desc: "Drag-and-drop video upload with real-time SSE job progress." },
  { icon: SearchIcon, title: "Search", to: "/search", desc: "Five search modes: keyword, text vector, visual, hybrid, visual hybrid." },
  { icon: CampaignsIcon, title: "Campaigns", to: "/campaigns", desc: "Auto-discover ad campaigns, research, and curate groupings." },
  { icon: ChatIcon, title: "Agent", to: "/agent", desc: "Natural-language queries over your ad database with tool-calling." },
  { icon: FlowIcon, title: "Jobs", to: "/pipelines", desc: "Pipeline orchestration with restartable stages and live progress." },
  { icon: LayersIcon, title: "Taxonomy", to: "/taxonomy", desc: "IAB Product Taxonomy 2.0, Content Taxonomy 3.1, and custom categories." },
  { icon: SettingsIcon, title: "Settings", to: "/settings", desc: "Configure VLM endpoints, OCR, Whisper, embeddings, and search." },
];

/* Component. */
export function About() {
  const [activeStage, setActiveStage] = useState<number | null>(null);

  const pipelineLines = useMemo(() => {
    const lines: React.ReactNode[] = [];
    PIPELINE_STAGES.forEach((s, i) => {
      lines.push(
        <div
          key={s.num}
          className="about-pipeline-stage"
          onMouseEnter={() => setActiveStage(i)}
          onMouseLeave={() => setActiveStage(null)}
          data-active={activeStage === i}
        >
          <div className="about-pipeline-num" style={{ color: s.color }}>
            {s.num}
          </div>
          <div className="about-pipeline-body">
            <div className="about-pipeline-title">{s.title}</div>
            <div className="about-pipeline-desc">{s.desc}</div>
          </div>
        </div>
      );
      if (i < PIPELINE_STAGES.length - 1) {
        lines.push(
          <div key={`line-${i}`} className="about-pipeline-line" />
        );
      }
    });
    return lines;
  }, [activeStage]);

  return (
    <div className="about-page">
      {/* Hero */}
      <div className="about-hero">
        <div className="about-hero-bg">
          <img src={bannerUrl} alt="" />
        </div>
        <div className="about-hero-overlay" />
        <div className="about-hero-content">
          <div className="about-eyebrow">
            <span className="about-dot" />
            Ad Retrieval, Graphing &amp; Understanding System
          </div>
          <h1 className="about-hero-title">ARGUS</h1>
          <p className="about-hero-sub">
            Local-first multimodal ad analysis. Ingest video ads, extract marketing
            entities, classify against taxonomies, search by text or visual embedding,
            discover campaigns, and query through a natural-language agent.
          </p>
          <div className="about-hero-actions">
            <Link to="/library" className="about-btn about-btn-primary">
              Open Library
            </Link>
            <Link to="/upload" className="about-btn">
              Upload Video
            </Link>
            <Link to="/agent" className="about-btn">
              Ask Agent
            </Link>
          </div>
        </div>
      </div>

      {/* Metrics strip */}
      <div className="about-metrics">
        <div className="about-metric">
          <span className="about-metric-label">Storage</span>
          <strong>SQLite + FTS5 + sqlite-vec</strong>
        </div>
        <div className="about-metric">
          <span className="about-metric-label">Text Embeddings</span>
          <strong>MiniLM-L6-v2</strong>
        </div>
        <div className="about-metric">
          <span className="about-metric-label">Visual Embeddings</span>
          <strong>SigLIP 2 frame vectors</strong>
        </div>
        <div className="about-metric">
          <span className="about-metric-label">Pipeline Stages</span>
          <strong>
            <CountUp target={10} />
          </strong>
        </div>
      </div>

      {/* Mission */}
      <FadeSection className="about-section" id="mission">
        <div className="about-section-head">
          <span className="about-section-num">01</span>
          <h2>System Mission</h2>
        </div>
        <div className="about-section-body">
          <p className="about-lead">
            ARGUS converts local video advertisements into structured, searchable,
            analyst-ready records. It is categorization-only: the system does not
            approve, block, gate, or escalate ads. Risk labels are descriptive
            observation tags for analysis and search.
          </p>
          <div className="about-card-grid about-card-grid-3">
            <div className="about-card">
              <strong>Local First</strong>
              <p>SQLite, local artifacts, local worker, local-first model endpoints. No Docker required by default.</p>
            </div>
            <div className="about-card">
              <strong>Evidence Grounded</strong>
              <p>OCR, transcripts, rules, frames, VLM evidence, and marketing entities all retain source context and traceability.</p>
            </div>
            <div className="about-card">
              <strong>Analyst Usable</strong>
              <p>Search, campaign grouping, research briefs, and the agent expose practical marketing analysis value.</p>
            </div>
          </div>
        </div>
      </FadeSection>

      {/* Architecture */}
      <FadeSection className="about-section" id="architecture">
        <div className="about-section-head">
          <span className="about-section-num">02</span>
          <h2>Architecture</h2>
        </div>
        <div className="about-section-body">
          <p>
            The backend owns ingestion, persistence, retrieval, campaign logic, and
            agent tools. The frontend is decoupled and communicates through JSON
            endpoints and SSE streams. Data lives in one SQLite database plus local
            artifact directories.
          </p>
          <div className="about-flow">
            <div className="about-flow-node">
              <span>Input</span>
              <strong>Video upload &amp; metadata</strong>
            </div>
            <div className="about-flow-arrow" />
            <div className="about-flow-node">
              <span>Worker</span>
              <strong>Frames, audio, OCR, transcript</strong>
            </div>
            <div className="about-flow-arrow" />
            <div className="about-flow-node">
              <span>Reasoning</span>
              <strong>Rules, VLM, entities</strong>
            </div>
            <div className="about-flow-arrow" />
            <div className="about-flow-node">
              <span>Index</span>
              <strong>FTS5, text &amp; frame vectors</strong>
            </div>
            <div className="about-flow-arrow" />
            <div className="about-flow-node">
              <span>Surface</span>
              <strong>API, React UI, agent</strong>
            </div>
          </div>
          <div className="about-table-wrap">
            <table className="about-table">
              <thead>
                <tr>
                  <th>Layer</th>
                  <th>Implementation</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>API</td><td>FastAPI</td><td>JSON endpoints and SSE streams for job and agent progress.</td></tr>
                <tr><td>Worker</td><td>Python stage orchestration</td><td>Restartable, logs every degraded path, reuses artifacts unless forced.</td></tr>
                <tr><td>Database</td><td>SQLite WAL</td><td>Concurrent API reads and worker writes, with FTS5 and sqlite-vec.</td></tr>
                <tr><td>Frontend</td><td>Vite, React, TypeScript</td><td>Consumes HTTP/SSE only; dev proxy forwards /api and /data.</td></tr>
                <tr><td>Inference</td><td>OpenAI-compatible engine</td><td>VLM, agent, OCR cleanup, self-correction, optional GLM-OCR.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </FadeSection>

      {/* Pipeline */}
      <FadeSection className="about-section" id="pipeline">
        <div className="about-section-head">
          <span className="about-section-num">03</span>
          <h2>Pipeline Stages</h2>
        </div>
        <div className="about-section-body">
          <p>
            ARGUS is a staged pipeline. Each stage writes structured artifacts or
            database rows that later stages can reuse, inspect, or search. The worker
            is the orchestrator; individual modules stay behind narrow interfaces.
          </p>
          <div className="about-pipeline">{pipelineLines}</div>
        </div>
      </FadeSection>

      {/* Models */}
      <FadeSection className="about-section" id="models">
        <div className="about-section-head">
          <span className="about-section-num">04</span>
          <h2>Model Responsibilities</h2>
        </div>
        <div className="about-section-body">
          <div className="about-table-wrap">
            <table className="about-table">
              <thead>
                <tr>
                  <th>Model / Engine</th>
                  <th>Responsibility</th>
                  <th>Grounding Rule</th>
                </tr>
              </thead>
              <tbody>
                {MODELS.map((m) => (
                  <tr key={m.name}>
                    <td style={{ color: "var(--fg)", fontWeight: 500 }}>{m.name}</td>
                    <td>{m.role}</td>
                    <td>{m.grounding}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </FadeSection>

      {/* Search */}
      <FadeSection className="about-section" id="search">
        <div className="about-section-head">
          <span className="about-section-num">05</span>
          <h2>Search &amp; Ranking</h2>
        </div>
        <div className="about-section-body">
          <p>
            Five retrieval modes power analyst workflows. Hybrid search uses
            reciprocal rank fusion over keyword and vector ranks. Visual queries
            expand into phrase sets and keep the best cosine match per ad.
          </p>
          <div className="about-table-wrap">
            <table className="about-table">
              <thead>
                <tr>
                  <th>Mode</th>
                  <th>Main Signal</th>
                  <th>Best For</th>
                </tr>
              </thead>
              <tbody>
                {SEARCH_MODES.map((s) => (
                  <tr key={s.mode}>
                    <td style={{ color: "var(--fg)", fontWeight: 500 }}>{s.mode}</td>
                    <td><code>{s.signal}</code></td>
                    <td>{s.best}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="about-note">
            <strong>Visual query examples:</strong> <code>red car</code>,{" "}
            <code>candidate podium</code>, <code>small disclaimer</code>,{" "}
            <code>product hero shot</code>, <code>before and after comparison</code>,{" "}
            <code>doctor office</code>, <code>mobile app screen</code>.
          </div>
        </div>
      </FadeSection>

      {/* Dedup */}
      <FadeSection className="about-section" id="dedup">
        <div className="about-section-head">
          <span className="about-section-num">06</span>
          <h2>Deduplication &amp; Related Ads</h2>
        </div>
        <div className="about-section-body">
          <p>
            Three similarity concepts answer different questions. Post-OCR duplicate
            detection is intentionally conservative: two ads with the same footage
            but different end cards remain separate and become campaign variants.
          </p>
          <div className="about-table-wrap">
            <table className="about-table">
              <thead>
                <tr>
                  <th>Layer</th>
                  <th>Signal</th>
                  <th>Purpose</th>
                </tr>
              </thead>
              <tbody>
                {DEDUP_LAYERS.map((d) => (
                  <tr key={d.layer}>
                    <td style={{ color: "var(--fg)", fontWeight: 500 }}>{d.layer}</td>
                    <td>{d.signal}</td>
                    <td>{d.purpose}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </FadeSection>

      {/* Campaigns */}
      <FadeSection className="about-section" id="campaigns">
        <div className="about-section-head">
          <span className="about-section-num">07</span>
          <h2>Campaign Discovery &amp; Research</h2>
        </div>
        <div className="about-section-body">
          <p>
            Campaign discovery is user-triggered and proposes clusters from repeated
            VLM campaign signals and brand-scoped visual vectors. No names are
            hardcoded. Accepted proposals become curated truth, protected from
            automatic rediscovery.
          </p>
          <div className="about-card-grid">
            <div className="about-card">
              <strong>Discovery Signals</strong>
              <p>Repeated VLM-extracted campaign names, shared offers, brand-scoped visual cohesion.</p>
            </div>
            <div className="about-card">
              <strong>Manual Controls</strong>
              <p>Create, edit, delete, assign and remove ads, accept reviewed proposals.</p>
            </div>
            <div className="about-card">
              <strong>Research Agent</strong>
              <p>Builds a local evidence bundle: findings, creative review, edits, open questions, answers.</p>
            </div>
            <div className="about-card">
              <strong>Future Expansion</strong>
              <p>Request contract already carries web and thinking flags for later advertiser-site research.</p>
            </div>
          </div>
        </div>
      </FadeSection>

      {/* Agent */}
      <FadeSection className="about-section" id="agent">
        <div className="about-section-head">
          <span className="about-section-num">08</span>
          <h2>Read-Only Agent</h2>
        </div>
        <div className="about-section-body">
          <p>
            The agent is tool-calling, not raw text-to-SQL. It has a fixed catalog
            of read-only tools for listing, counting, aggregating, searching, and a
            bounded SQL escape hatch. Database connections use{" "}
            <code>PRAGMA query_only = ON</code>.
          </p>
          <ul className="about-list">
            <li>Fixed tool catalog: list, count, aggregate, detail, FTS, vector, hybrid, bounded SQL.</li>
            <li>Sessions, messages, tool calls, and tool results are fully audited.</li>
            <li>Answers cite real ad_id and campaign_id values only.</li>
            <li>SQL escape hatch is capped and time-limited.</li>
          </ul>
        </div>
      </FadeSection>

      {/* Features / UI pages */}
      <FadeSection className="about-section" id="features">
        <div className="about-section-head">
          <span className="about-section-num">09</span>
          <h2>Application Features</h2>
        </div>
        <div className="about-section-body">
          <div className="about-card-grid about-card-grid-4">
            {FEATURES.map((f) => {
              const Icon = f.icon;
              return (
                <Link key={f.title} to={f.to} className="about-card about-card-link">
                  <Icon className="about-card-icon" />
                  <strong>{f.title}</strong>
                  <p>{f.desc}</p>
                </Link>
              );
            })}
          </div>
        </div>
      </FadeSection>

      {/* Output contract */}
      <FadeSection className="about-section" id="output">
        <div className="about-section-head">
          <span className="about-section-num">10</span>
          <h2>Output Contract</h2>
        </div>
        <div className="about-section-body">
          <p>
            Final classification is strict JSON including category, confidence,
            observation tags, evidence with timestamps, marketing entities, related
            ads, and debug records. Projection columns on the ads table are written
            in the same transaction for fast listing.
          </p>
          <pre className="about-pre"><code>{`{
  "ad_id": "ad_xxxxxxxx",
  "primary_category": "automotive",
  "risk_labels": ["deceptive_urgency"],
  "confidence": 0.92,
  "evidence": [
    {
      "time_ms": 14000,
      "frame_index": 28,
      "source": "ocr",
      "text": "$299/mo for 36 months",
      "confidence": 0.87
    }
  ],
  "marketing_entities": {
    "brand": { "name": "Jeep", "logo_present": true },
    "products": ["Grand Cherokee", "Wrangler"],
    "offers": ["$299/mo 36-mo lease"],
    "ctas": ["Shop now"],
    "disclaimers": []
  },
  "related_ads": {
    "exact_duplicate_of": null,
    "near_duplicate_of": null,
    "semantically_similar": []
  }
}`}</code></pre>
        </div>
      </FadeSection>

      {/* Persistence */}
      <FadeSection className="about-section" id="persistence">
        <div className="about-section-head">
          <span className="about-section-num">11</span>
          <h2>Data Model</h2>
        </div>
        <div className="about-section-body">
          <p>
            SQLite is the system of record. JSON columns remain authoritative while
            projection columns on <code>ads</code> keep list views and filters fast.
          </p>
          <div className="about-card-grid">
            <div className="about-card"><strong>ads</strong><p>Source path, status, hashes, brand/product/category projections, duplicate metadata.</p></div>
            <div className="about-card"><strong>frames</strong><p>Frame path, timestamp, pHash, kept/dropped markers, blur/blank indicators.</p></div>
            <div className="about-card"><strong>ocr_items</strong><p>Engine-specific OCR text, confidence, bounding boxes, frame source.</p></div>
            <div className="about-card"><strong>transcript_segments</strong><p>Timestamped transcript evidence from Whisper backends.</p></div>
            <div className="about-card"><strong>classifications</strong><p>Primary category, confidence, observation tags, OCR quality, evidence JSON.</p></div>
            <div className="about-card"><strong>marketing_entities</strong><p>Brand, advertiser, products, offers, prices, CTAs, social proof, disclaimers.</p></div>
            <div className="about-card"><strong>campaigns / ad_campaigns</strong><p>User and auto campaign records, assignment source, similarity scores.</p></div>
            <div className="about-card"><strong>agent_sessions / messages</strong><p>Audited agent runs, messages, tool calls, and tool results.</p></div>
          </div>
          <div className="about-note" style={{ marginTop: 16 }}>
            <strong>Vector tables:</strong> <code>vec_ads_text</code>, <code>vec_ads_visual</code>,{" "}
            <code>vec_frames_visual</code> store sqlite-vec embeddings. Per-frame visual vectors let visual
            queries return the best matching frame, not just a whole-ad score.
          </div>
        </div>
      </FadeSection>

      {/* GPU */}
      <FadeSection className="about-section" id="gpu">
        <div className="about-section-head">
          <span className="about-section-num">12</span>
          <h2>GPU Acceleration</h2>
        </div>
        <div className="about-section-body">
          <p>
            Different components use different acceleration paths. ARGUS supports
            NVIDIA CUDA, AMD ROCm, and CPU fallback.
          </p>
          <div className="about-table-wrap">
            <table className="about-table">
              <thead>
                <tr>
                  <th>Component</th>
                  <th>Uses GPU When</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>VLM Classification</td><td>Inference engine is configured for GPU</td></tr>
                <tr><td>GLM-OCR</td><td>GLM-OCR inference engine is configured for GPU</td></tr>
                <tr><td>Whisper Transcript</td><td><code>use_gpu: true</code> and driver supports it</td></tr>
                <tr><td>PaddleOCR</td><td>Usually CPU by default</td></tr>
                <tr><td>MiniLM Text Embeddings</td><td><code>device: cuda</code> and torch GPU available</td></tr>
                <tr><td>SigLIP 2 Visual Embeddings</td><td><code>device: cuda</code> and torch GPU available</td></tr>
                <tr><td>Visual Vector Search</td><td>SigLIP 2 loads through GPU-enabled torch</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </FadeSection>

      {/* API */}
      <FadeSection className="about-section" id="api">
        <div className="about-section-head">
          <span className="about-section-num">13</span>
          <h2>API Endpoints</h2>
        </div>
        <div className="about-section-body">
          <div className="about-table-wrap">
            <table className="about-table">
              <thead>
                <tr>
                  <th>Method</th>
                  <th>Endpoint</th>
                  <th>Purpose</th>
                </tr>
              </thead>
              <tbody>
                <tr><td><code>POST</code></td><td>/api/ads/upload</td><td>Upload a video and create a job</td></tr>
                <tr><td><code>GET</code></td><td>/api/ads</td><td>List ads with filters</td></tr>
                <tr><td><code>GET</code></td><td>/api/ads/:id</td><td>Fetch ad detail, classification, entities</td></tr>
                <tr><td><code>GET</code></td><td>/api/ads/:id/frames</td><td>Fetch frame metadata</td></tr>
                <tr><td><code>GET</code></td><td>/api/ads/:id/evidence</td><td>Fetch evidence and rule triggers</td></tr>
                <tr><td><code>GET</code></td><td>/api/ads/:id/similar</td><td>Retrieve similar ads</td></tr>
                <tr><td><code>GET</code></td><td>/api/search</td><td>Keyword, text vector, visual, or hybrid search</td></tr>
                <tr><td><code>POST</code></td><td>/api/campaigns/discover</td><td>Scan campaign proposals</td></tr>
                <tr><td><code>POST</code></td><td>/api/campaigns/discover/accept</td><td>Accept proposals as user assignments</td></tr>
                <tr><td><code>POST</code></td><td>/api/campaigns/:id/ads</td><td>Manually assign ads to a campaign</td></tr>
                <tr><td><code>POST</code></td><td>/api/campaigns/:id/research/deep</td><td>Run local campaign research</td></tr>
                <tr><td><code>GET</code></td><td>/api/jobs/:id/events</td><td>Stream job progress (SSE)</td></tr>
                <tr><td><code>GET</code></td><td>/api/agent/sessions/:id/events</td><td>Stream agent responses (SSE)</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </FadeSection>

      {/* Footer */}
      <div className="about-footer">
        <div className="about-footer-brand">
          <img src={logoUrl} alt="" />
          <div>
            <strong>ARGUS</strong>
            <span>Ad Retrieval, Graphing &amp; Understanding System</span>
          </div>
        </div>
        <p>
          Local-first multimodal ad intelligence. No Docker, no cloud services
          required by default. Built with FastAPI, React, SQLite, and
          OpenAI-compatible vision-language models.
        </p>
      </div>
    </div>
  );
}
