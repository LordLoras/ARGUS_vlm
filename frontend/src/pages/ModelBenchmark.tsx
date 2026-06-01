import {
  AlertTriangle,
  BarChart3,
  BrainCircuit,
  Clock3,
  Gauge,
  LineChart,
  Server,
  ShieldCheck
} from "lucide-react";

import { Topbar } from "../components/Topbar";
import benchmarkData from "../data/modelBenchmarkResults.json";

type BenchmarkAd = {
  id: string;
  label: string;
  brand: string;
  category: string;
  difficulty: string;
  duration_s: number;
  frame_count: number;
  kept_frames: number;
  ocr_items: number;
  transcript_segments: number;
  focus: string[];
};

type BenchmarkCase = {
  ad_id: string;
  score: number;
  seconds: number;
  ok: boolean;
  parse_ok: boolean;
  error?: string | null;
  note: string;
  breakdown: Record<string, number>;
};

type BenchmarkModel = {
  id: string;
  name: string;
  provider: string;
  route_type: "OpenRouter" | "Local" | string;
  endpoint: string;
  model: string;
  thinking_off: string;
  score: number;
  completion_seconds: number;
  successful_ads: number;
  total_ads: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: number;
  relative_performance_pct: number;
  performance_price_index: number | null;
  readout: string;
  cases: BenchmarkCase[];
};

type BenchmarkPayload = {
  generated_at: string;
  benchmark_date_label: string;
  source: string;
  raw_output_path: string;
  protocol: Record<string, string | number>;
  ads: BenchmarkAd[];
  models: BenchmarkModel[];
};

const data = benchmarkData as BenchmarkPayload;

export function ModelBenchmark() {
  const models = data.models;
  const completedModels = models.filter((model) => model.successful_ads > 0);
  const qualityLeader = completedModels[0] ?? models[0];
  const fastestPaid = completedModels
    .filter((model) => model.route_type === "OpenRouter")
    .reduce((best, model) => (model.completion_seconds < best.completion_seconds ? model : best), completedModels[0]);
  const failures = models.filter((model) => model.successful_ads === 0);
  const orderedAds = data.ads;

  return (
    <>
      <Topbar crumbs={["Intelligence", "Model Benchmark"]} />
      <main className="page benchmark-page">
        <section className="benchmark-hero">
          <div>
            <span className="eyebrow">Measured visitor benchmark</span>
            <h1>VLM routes scored on five existing ad artifacts</h1>
            <p>
              Real OpenRouter and local endpoint calls using selected frames, OCR, transcript,
              and metadata from the local ARGUS database. Scores are computed by an automatic
              rubric against persisted ARGUS reference fields.
            </p>
          </div>
          <div className="benchmark-hero-grid" aria-label="Benchmark highlights">
            <BenchmarkStat icon={BrainCircuit} label="Quality leader" value={qualityLeader?.name ?? "N/A"} detail={`${qualityLeader?.score.toFixed(1) ?? "0.0"} / 100`} />
            <BenchmarkStat icon={Clock3} label="Fastest completed paid" value={fastestPaid?.name ?? "N/A"} detail={`${formatSeconds(fastestPaid?.completion_seconds ?? 0)} for 5 ads`} />
            <BenchmarkStat icon={Gauge} label="Measured routes" value={`${completedModels.length}/${models.length}`} detail="actual scored calls" />
            <BenchmarkStat icon={ShieldCheck} label="Thinking" value="Disabled where allowed" detail={data.protocol.openrouter_thinking as string} />
          </div>
        </section>

        {failures.length > 0 ? (
          <section className="benchmark-alert">
            <AlertTriangle size={16} />
            <div>
              <strong>{failures.length} route{failures.length === 1 ? "" : "s"} did not produce scored results.</strong>
              <p>
                Failed routes remain visible as measured failures rather than being estimated
                or replaced with projected numbers.
              </p>
            </div>
          </section>
        ) : null}

        <section className="benchmark-protocol">
          <div className="benchmark-protocol-card">
            <Server size={16} />
            <div>
              <span>Run controls</span>
              <strong>Actual calls, JSON output, measured rows only</strong>
              <p>
                Temperature: <code>{data.protocol.temperature}</code>.
                OpenRouter thinking control: <code>{data.protocol.openrouter_thinking}</code>.
                Local control: <code>{data.protocol.local_thinking}</code>.
              </p>
            </div>
          </div>
          <div className="benchmark-protocol-card">
            <Gauge size={16} />
            <div>
              <span>Quality metric</span>
              <strong>Schema, category, brand, products, offers, evidence</strong>
              <p>{data.protocol.scoring}</p>
            </div>
          </div>
          <div className="benchmark-protocol-card">
            <LineChart size={16} />
            <div>
              <span>Run record</span>
              <strong>{formatDate(data.generated_at)} / {data.benchmark_date_label}</strong>
              <p>
                Raw outputs are stored locally at <code>{data.raw_output_path}</code> when
                the benchmark runner is executed. The page shows measured endpoint rows only;
                projected results are not mixed into the table.
              </p>
            </div>
          </div>
        </section>

        <section className="benchmark-section">
          <div className="benchmark-section-head">
            <div>
              <span className="eyebrow">Model stack</span>
              <h2>Aggregate five-ad result</h2>
            </div>
            <span className="badge badge-emerald">Actual calls</span>
          </div>
          <div className="benchmark-table-wrap">
            <table className="benchmark-table">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Quality</th>
                  <th>Vs leader</th>
                  <th>Completion</th>
                  <th>Tokens</th>
                  <th>5-ad cost</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {models.map((model) => (
                  <tr key={model.id} className={model.successful_ads === 0 ? "is-failed" : undefined}>
                    <td>
                      <div className="benchmark-model-cell">
                        <strong>{model.name}</strong>
                        <span>{model.id}</span>
                        <em>{model.endpoint}</em>
                      </div>
                    </td>
                    <td>
                      <MetricBar value={model.score} max={100} label={`${model.score.toFixed(1)}`} />
                    </td>
                    <td>{model.relative_performance_pct.toFixed(1)}%</td>
                    <td>{formatSeconds(model.completion_seconds)}</td>
                    <td>{formatTokens(model.prompt_tokens, model.completion_tokens)}</td>
                    <td>{formatCost(model)}</td>
                    <td>
                      <div className="benchmark-status-cell">
                        <strong>{model.successful_ads}/{model.total_ads} complete</strong>
                        <span>{model.readout}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="benchmark-section">
          <div className="benchmark-section-head">
            <div>
              <span className="eyebrow">Artifacts</span>
              <h2>Five-ad ladder</h2>
            </div>
            <span className="benchmark-token-pill">
              {completedModels[0]?.prompt_tokens.toLocaleString() ?? 0} prompt tokens on top completed row
            </span>
          </div>
          <div className="benchmark-ad-grid">
            {data.ads.map((ad) => (
              <article className="benchmark-ad-card" key={ad.id}>
                <div className="benchmark-ad-top">
                  <span className={`benchmark-difficulty is-${ad.difficulty.toLowerCase()}`}>
                    {ad.difficulty}
                  </span>
                  <span>{ad.duration_s.toFixed(1)}s</span>
                </div>
                <h3>{ad.label}</h3>
                <p>{ad.brand} / {ad.category}</p>
                <div className="benchmark-ad-metrics">
                  <span><b>{ad.kept_frames}</b> kept frames</span>
                  <span><b>{ad.ocr_items}</b> OCR items</span>
                  <span><b>{ad.transcript_segments}</b> transcript</span>
                </div>
                <div className="benchmark-focus-list">
                  {ad.focus.map((item) => <span key={item}>{item}</span>)}
                </div>
                <code>{ad.id}</code>
              </article>
            ))}
          </div>
        </section>

        <section className="benchmark-section">
          <div className="benchmark-section-head">
            <div>
              <span className="eyebrow">Per-ad detail</span>
              <h2>Score and completion matrix</h2>
            </div>
          </div>
          <div className="benchmark-matrix-card" role="table" aria-label="Per-ad benchmark comparison">
            <div className="benchmark-matrix-header" role="row">
              <div className="benchmark-matrix-corner" role="columnheader">
                <span>Route</span>
                <strong>Model and aggregate</strong>
              </div>
              {orderedAds.map((ad) => (
                <div className="benchmark-matrix-ad-head" role="columnheader" key={ad.id}>
                  <span className={`benchmark-difficulty is-${ad.difficulty.toLowerCase()}`}>{ad.difficulty}</span>
                  <strong>{ad.brand}</strong>
                  <em>{ad.label}</em>
                </div>
              ))}
            </div>
            {models.map((model) => (
              <article className="benchmark-matrix-row" role="row" key={model.id}>
                <div className="benchmark-matrix-route" role="rowheader">
                  <strong>{model.name}</strong>
                  <span>{model.provider} / {model.route_type}</span>
                  <em>
                    {model.score.toFixed(1)} avg · {formatSeconds(model.completion_seconds)}
                  </em>
                </div>
                {orderedAds.map((ad) => {
                  const item = model.cases.find((candidate) => candidate.ad_id === ad.id);
                  return item ? (
                    <div className={caseClassName(item)} role="cell" key={`${model.id}-${ad.id}`}>
                      <div className="benchmark-case-scoreline">
                        <strong>{item.score.toFixed(1)}</strong>
                        <span>{item.ok ? formatSeconds(item.seconds) : "failed"}</span>
                      </div>
                      <div className="benchmark-case-track" aria-hidden="true">
                        <span style={{ width: `${Math.max(3, Math.min(100, item.score))}%` }} />
                      </div>
                      <p>{item.ok ? item.note : shortError(item.error)}</p>
                    </div>
                  ) : (
                    <div className="benchmark-case is-failed" role="cell" key={`${model.id}-${ad.id}`}>
                      <div className="benchmark-case-scoreline">
                        <strong>0.0</strong>
                        <span>missing</span>
                      </div>
                      <p>No recorded run for this artifact.</p>
                    </div>
                  );
                })}
              </article>
            ))}
          </div>
        </section>
      </main>
    </>
  );
}

function BenchmarkStat({
  icon: Icon,
  label,
  value,
  detail
}: {
  icon: typeof BarChart3;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="benchmark-stat">
      <Icon size={16} />
      <span>{label}</span>
      <strong>{value}</strong>
      <em>{detail}</em>
    </div>
  );
}

function MetricBar({ value, max, label }: { value: number; max: number; label: string }) {
  return (
    <div className="benchmark-meter">
      <span style={{ width: `${Math.max(3, Math.min(100, (value / max) * 100))}%` }} />
      <strong>{label}</strong>
    </div>
  );
}

function formatSeconds(seconds: number) {
  if (seconds <= 0) return "0s";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

function formatTokens(prompt: number, completion: number) {
  if (!prompt && !completion) return "none";
  return `${prompt.toLocaleString()} / ${completion.toLocaleString()}`;
}

function formatCost(model: BenchmarkModel) {
  if (model.route_type === "Local") return "$0 provider";
  if (model.route_type === "Remote") return "custom";
  if (!model.estimated_cost_usd) return "N/A";
  return `$${model.estimated_cost_usd.toFixed(4)}`;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function shortError(error?: string | null) {
  if (!error) return "No response.";
  if (error.includes("Reasoning is mandatory")) return "Provider requires reasoning.";
  if (error.includes("actively refused")) return "Endpoint refused connection.";
  return error.length > 78 ? `${error.slice(0, 75)}...` : error;
}

function caseClassName(item: BenchmarkCase) {
  if (!item.ok) return "benchmark-case is-failed";
  if (item.score >= 92) return "benchmark-case is-strong";
  if (item.score >= 85) return "benchmark-case is-good";
  return "benchmark-case is-low";
}
