import { EndpointEditor, NumberField, ToggleField, endpointTitle } from "./Fields";
import { VLM_ENDPOINTS, type UpdateSettingsDraft, type VlmEndpointKey } from "./types";
import type { ApiKeyRecord, SettingsConfig } from "../../lib/types";
import { cn } from "../../lib/utils";

export function ModelSettings({
  config,
  apiKeys,
  modeOptions,
  responseFormats,
  updateDraft
}: {
  config: SettingsConfig;
  apiKeys: ApiKeyRecord[];
  modeOptions: Array<{ value: string; label: string; description: string }>;
  responseFormats: string[];
  updateDraft: UpdateSettingsDraft;
}) {
  const active = config.vlm[config.vlm.mode as VlmEndpointKey] ?? config.vlm.local;
  const activeKey = apiKeys.find((item) => item.name === active.api_key_env);

  return (
    <div className="settings-stack">
      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>VLM Routing</h2>
            <p>Choose the endpoint preset used by ingest, creative panels, and inherited agent calls.</p>
          </div>
          <span className={cn("badge", activeKey?.available ? "badge-emerald" : "badge-mono")}>
            {active.api_key_env ? `${active.api_key_env} ${activeKey?.available ? "ready" : "missing"}` : "no key"}
          </span>
        </div>

        <div className="settings-mode-grid">
          {modeOptions.map((mode) => (
            <button
              key={mode.value}
              className={cn("settings-mode", config.vlm.mode === mode.value && "active")}
              onClick={() =>
                updateDraft((current) => ({
                  ...current,
                  vlm: { ...current.vlm, mode: mode.value }
                }))
              }
            >
              <strong>{mode.label}</strong>
              <span>{mode.description}</span>
            </button>
          ))}
        </div>

        <div className="settings-grid">
          <NumberField
            label="Max frames"
            description="Selected frames sent to the VLM evidence bundle."
            value={config.vlm.max_frames_in_bundle}
            min={1}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                vlm: { ...current.vlm, max_frames_in_bundle: value }
              }))
            }
          />
          <NumberField
            label="Image max dim"
            description="Largest pixel dimension for VLM frame images."
            value={config.vlm.image_max_dim}
            min={128}
            max={2048}
            onChange={(value) =>
              updateDraft((current) => ({ ...current, vlm: { ...current.vlm, image_max_dim: value } }))
            }
          />
          <Toggle
            label="OCR cleanup"
            description="Text-only pass that repairs garbled OCR before classification."
            checked={config.vlm.enable_ocr_cleanup_pass}
            field="enable_ocr_cleanup_pass"
            updateDraft={updateDraft}
          />
          <Toggle
            label="Self correction"
            description="Consistency pass after the verifier result."
            checked={config.vlm.enable_self_correction}
            field="enable_self_correction"
            updateDraft={updateDraft}
          />
          <Toggle
            label="Post validation"
            description="Deterministic validation of grounded extraction fields."
            checked={config.vlm.enable_post_validation}
            field="enable_post_validation"
            updateDraft={updateDraft}
          />
          <Toggle
            label="Visual verify"
            description="Second VLM pass to verify logo and brand claims."
            checked={config.vlm.enable_visual_verify}
            field="enable_visual_verify"
            updateDraft={updateDraft}
          />
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>Endpoint Presets</h2>
            <p>Only the selected preset is active. API key fields store variable names, not secret values.</p>
          </div>
        </div>
        <div className="settings-endpoints">
          {VLM_ENDPOINTS.map((mode) => (
            <EndpointEditor
              key={mode}
              title={endpointTitle(mode)}
              active={config.vlm.mode === mode}
              endpoint={config.vlm[mode]}
              apiKeys={apiKeys}
              responseFormats={responseFormats}
              onChange={(patch) =>
                updateDraft((current) => ({
                  ...current,
                  vlm: {
                    ...current.vlm,
                    [mode]: { ...current.vlm[mode], ...patch }
                  }
                }))
              }
            />
          ))}
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>Agent</h2>
            <p>Keep inherited mode on when the analyst agent should follow the active VLM route.</p>
          </div>
        </div>
        <div className="settings-grid">
          <ToggleField
            label="Inherit VLM"
            description="Agent endpoint follows the selected VLM preset."
            checked={config.agent.inherit_vlm}
            onChange={(checked) =>
              updateDraft((current) => ({
                ...current,
                agent: { ...current.agent, inherit_vlm: checked }
              }))
            }
          />
          <NumberField
            label="Max iterations"
            description="Maximum tool-call turns for one agent answer."
            value={config.agent.max_iterations}
            min={1}
            max={32}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                agent: { ...current.agent, max_iterations: value }
              }))
            }
          />
          <NumberField
            label="Agent max tokens"
            description="Generation budget for one agent response."
            value={config.agent.max_tokens}
            min={64}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                agent: { ...current.agent, max_tokens: value }
              }))
            }
          />
          <NumberField
            label="Agent temperature"
            description="Lower is more deterministic."
            value={config.agent.temperature}
            min={0}
            max={2}
            step={0.1}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                agent: { ...current.agent, temperature: value }
              }))
            }
          />
        </div>
      </section>
    </div>
  );
}

function Toggle({
  label,
  description,
  checked,
  field,
  updateDraft
}: {
  label: string;
  description: string;
  checked: boolean;
  field: keyof Pick<
    SettingsConfig["vlm"],
    | "enable_ocr_cleanup_pass"
    | "enable_self_correction"
    | "enable_post_validation"
    | "enable_visual_verify"
  >;
  updateDraft: UpdateSettingsDraft;
}) {
  return (
    <ToggleField
      label={label}
      description={description}
      checked={checked}
      onChange={(next) =>
        updateDraft((current) => ({
          ...current,
          vlm: { ...current.vlm, [field]: next }
        }))
      }
    />
  );
}
