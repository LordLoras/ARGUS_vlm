import { useEffect, useMemo, useState } from "react";

import { NumberField } from "./Fields";
import type { SettingsConfig } from "../../lib/types";

type CalculatorState = {
  ads: number;
  textChars: number;
  promptTokens: number;
  imageTokensPerFrame: number;
  verifierOutputTokens: number;
  cleanupInputTokens: number;
  cleanupOutputTokens: number;
  correctionInputTokens: number;
  correctionOutputTokens: number;
  visualVerifyInputTokens: number;
  visualVerifyOutputTokens: number;
  inputUsdPerMillion: number;
  outputUsdPerMillion: number;
};

type Row = {
  label: string;
  inputTokens: number;
  outputTokens: number;
  enabled: boolean;
};

const STORAGE_KEY = "argus:cost-calculator:v1";

const DEFAULTS: CalculatorState = {
  ads: 1,
  textChars: 3500,
  promptTokens: 18000,
  imageTokensPerFrame: 750,
  verifierOutputTokens: 2800,
  cleanupInputTokens: 5000,
  cleanupOutputTokens: 1200,
  correctionInputTokens: 4500,
  correctionOutputTokens: 400,
  visualVerifyInputTokens: 1200,
  visualVerifyOutputTokens: 300,
  inputUsdPerMillion: 1,
  outputUsdPerMillion: 3
};

export function CostCalculator({ config }: { config: SettingsConfig }) {
  const [state, setState] = useState<CalculatorState>(() => loadState());

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  const rows = useMemo(() => buildRows(config, state), [config, state]);
  const totalInput = rows.reduce((sum, row) => sum + (row.enabled ? row.inputTokens : 0), 0);
  const totalOutput = rows.reduce((sum, row) => sum + (row.enabled ? row.outputTokens : 0), 0);
  const perAd = estimateCost(totalInput, totalOutput, state);
  const batch = perAd * state.ads;
  const activeEndpoint = config.vlm[config.vlm.mode as "local" | "remote" | "frontier"] ?? config.vlm.local;

  const update = (patch: Partial<CalculatorState>) => {
    setState((current) => ({ ...current, ...patch }));
  };

  return (
    <div className="settings-stack">
      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>Token and Cost Estimate</h2>
            <p>
              Rough planning calculator for multimodal ingest. Enter the model price from the
              provider dashboard as dollars per 1M input and output tokens.
            </p>
          </div>
          <span className="badge badge-violet">{config.vlm.mode} / {activeEndpoint.model}</span>
        </div>

        <div className="cost-summary">
          <CostStat label="Input / ad" value={formatTokens(totalInput)} />
          <CostStat label="Output / ad" value={formatTokens(totalOutput)} />
          <CostStat label="Cost / ad" value={formatUsd(perAd)} />
          <CostStat label={`${state.ads} ads`} value={formatUsd(batch)} />
        </div>

        <div className="settings-grid">
          <NumberField
            label="Ads"
            description="Batch size to estimate."
            value={state.ads}
            min={1}
            onChange={(ads) => update({ ads })}
          />
          <NumberField
            label="Input $ / 1M"
            description="Provider input-token price."
            value={state.inputUsdPerMillion}
            min={0}
            step={0.01}
            onChange={(inputUsdPerMillion) => update({ inputUsdPerMillion })}
          />
          <NumberField
            label="Output $ / 1M"
            description="Provider output-token price."
            value={state.outputUsdPerMillion}
            min={0}
            step={0.01}
            onChange={(outputUsdPerMillion) => update({ outputUsdPerMillion })}
          />
          <NumberField
            label="Prompt tokens"
            description="Verifier prompt, schema, and taxonomies."
            value={state.promptTokens}
            min={0}
            onChange={(promptTokens) => update({ promptTokens })}
          />
          <NumberField
            label="Text chars"
            description="OCR plus transcript chars in the evidence bundle."
            value={state.textChars}
            min={0}
            onChange={(textChars) => update({ textChars })}
          />
          <NumberField
            label="Image tokens / frame"
            description="Model-specific vision token estimate."
            value={state.imageTokensPerFrame}
            min={0}
            onChange={(imageTokensPerFrame) => update({ imageTokensPerFrame })}
          />
          <NumberField
            label="Verifier output"
            description="Final structured JSON response tokens."
            value={state.verifierOutputTokens}
            min={0}
            onChange={(verifierOutputTokens) => update({ verifierOutputTokens })}
          />
          <NumberField
            label="Cleanup input"
            description="OCR cleanup pass input tokens."
            value={state.cleanupInputTokens}
            min={0}
            onChange={(cleanupInputTokens) => update({ cleanupInputTokens })}
          />
          <NumberField
            label="Cleanup output"
            description="OCR cleanup pass output tokens."
            value={state.cleanupOutputTokens}
            min={0}
            onChange={(cleanupOutputTokens) => update({ cleanupOutputTokens })}
          />
          <NumberField
            label="Correction input"
            description="Self-correction pass input tokens."
            value={state.correctionInputTokens}
            min={0}
            onChange={(correctionInputTokens) => update({ correctionInputTokens })}
          />
          <NumberField
            label="Correction output"
            description="Self-correction pass output tokens."
            value={state.correctionOutputTokens}
            min={0}
            onChange={(correctionOutputTokens) => update({ correctionOutputTokens })}
          />
          <NumberField
            label="Visual verify output"
            description="Optional logo/brand verification output tokens."
            value={state.visualVerifyOutputTokens}
            min={0}
            onChange={(visualVerifyOutputTokens) => update({ visualVerifyOutputTokens })}
          />
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>Pipeline Calls</h2>
            <p>Enabled rows are included in the estimate according to the current saved settings draft.</p>
          </div>
        </div>
        <div className="cost-table">
          <div className="cost-table-head">
            <span>Call</span>
            <span>Input</span>
            <span>Output</span>
            <span>Status</span>
          </div>
          {rows.map((row) => (
            <div key={row.label} className="cost-table-row">
              <span>{row.label}</span>
              <span className="mono">{formatTokens(row.inputTokens)}</span>
              <span className="mono">{formatTokens(row.outputTokens)}</span>
              <span className={`badge ${row.enabled ? "badge-emerald" : "badge-mono"}`}>
                {row.enabled ? "included" : "off"}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>OpenRouter Notes</h2>
            <p>
              Frontier mode uses the OpenAI-compatible OpenRouter base URL. Add
              OPENROUTER_API_KEY under API Keys, choose a model id in the Frontier preset, then
              switch VLM Routing to Frontier.
            </p>
          </div>
        </div>
        <div className="cost-notes">
          <span>Use provider pricing for the exact model; OpenRouter prices vary by route.</span>
          <span>Keep response format on json_schema for capable models; fall back to json_object if a route rejects schema output.</span>
          <span>Run one short ingest first and compare the actual bill with this estimate before batch uploads.</span>
        </div>
      </section>
    </div>
  );
}

function buildRows(config: SettingsConfig, state: CalculatorState): Row[] {
  const evidenceTextTokens = Math.ceil(state.textChars / 4);
  const frameCount = config.vlm.max_frames_in_bundle;
  const imageTokens = frameCount * state.imageTokensPerFrame;
  const visualVerifyInput = state.visualVerifyInputTokens + imageTokens;
  return [
    {
      label: "OCR cleanup",
      inputTokens: state.cleanupInputTokens,
      outputTokens: state.cleanupOutputTokens,
      enabled: config.vlm.enable_ocr_cleanup_pass
    },
    {
      label: "Verifier",
      inputTokens: state.promptTokens + evidenceTextTokens + imageTokens,
      outputTokens: state.verifierOutputTokens,
      enabled: true
    },
    {
      label: "Self correction",
      inputTokens: state.correctionInputTokens,
      outputTokens: state.correctionOutputTokens,
      enabled: config.vlm.enable_self_correction
    },
    {
      label: "Visual verify",
      inputTokens: visualVerifyInput,
      outputTokens: state.visualVerifyOutputTokens,
      enabled: config.vlm.enable_visual_verify
    }
  ];
}

function estimateCost(inputTokens: number, outputTokens: number, state: CalculatorState) {
  return (
    (inputTokens / 1_000_000) * state.inputUsdPerMillion +
    (outputTokens / 1_000_000) * state.outputUsdPerMillion
  );
}

function CostStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="cost-stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatTokens(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(value >= 10000 ? 1 : 2)}k`;
  return String(Math.round(value));
}

function formatUsd(value: number) {
  if (value < 0.01) return `$${value.toFixed(4)}`;
  if (value < 1) return `$${value.toFixed(3)}`;
  return `$${value.toFixed(2)}`;
}

function loadState(): CalculatorState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    return { ...DEFAULTS, ...JSON.parse(raw) } as CalculatorState;
  } catch {
    return DEFAULTS;
  }
}
