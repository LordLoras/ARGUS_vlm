import { EndpointEditor, NumberField, SelectField, ToggleField, endpointTitle } from "./Fields";
import {
  AGENT_INHERIT_ROUTES,
  VLM_ENDPOINTS,
  type AgentInheritRoute,
  type UpdateSettingsDraft,
  type VlmEndpointKey
} from "./types";
import type { ApiKeyRecord, EndpointSettings, SettingsConfig } from "../../lib/types";
import { cn } from "../../lib/utils";

export function ModelSettings({
  config,
  apiKeys,
  modeOptions,
  promptProfiles = DEFAULT_PROMPT_PROFILES,
  responseFormats,
  updateDraft
}: {
  config: SettingsConfig;
  apiKeys: ApiKeyRecord[];
  modeOptions: Array<{ value: string; label: string; description: string }>;
  promptProfiles?: Array<{ value: string; label: string; description: string }>;
  responseFormats: string[];
  updateDraft: UpdateSettingsDraft;
}) {
  const active = config.vlm[config.vlm.mode as VlmEndpointKey] ?? config.vlm.local;
  const activeKey = apiKeys.find((item) => item.name === active.api_key_env);
  const promptProfile = config.vlm.prompt_profile ?? "auto";
  const promptProfileLabels = Object.fromEntries(promptProfiles.map((item) => [item.value, item.label]));
  const selectedPromptProfile = promptProfiles.find((item) => item.value === promptProfile);
  const agent = normalizeAgent(config.agent);
  const creativePanel = normalizeCreativePanel(config.creative_panel);
  const agentInheritRoute = normalizeAgentInheritRoute(agent.inherit_vlm_mode);
  const agentInheritedKey = resolveAgentInheritedKey(config, agentInheritRoute);
  const agentInheritedEndpoint = config.vlm[agentInheritedKey];
  const agentInheritLabel = inheritRouteLabel(agentInheritRoute, agentInheritedKey);
  const agentEndpoint = toolEndpointForEditor(agent.endpoint, {
    temperature: agent.temperature,
    max_tokens: agent.max_tokens
  });
  const creativeEndpoint = toolEndpointForEditor(creativePanel.endpoint, {
    temperature: creativePanel.temperature,
    max_tokens: creativePanel.max_tokens
  });

  return (
    <div className="settings-stack">
      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>VLM Routing</h2>
            <p>Choose the endpoint preset used by ingest and by any AI tool still set to inherit VLM.</p>
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
          <SelectField
            label="Prompt profile"
            description={
              selectedPromptProfile?.description ??
              "Verifier prompt used for the selected ingest route."
            }
            value={promptProfile}
            options={promptProfiles.map((item) => item.value)}
            optionLabels={promptProfileLabels}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                vlm: { ...current.vlm, prompt_profile: value }
              }))
            }
          />
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
            <h2>Agent Research</h2>
            <p>Controls the chat agent and campaign deep research. Pin this locally to avoid Frontier tool loops.</p>
          </div>
          {agent.inherit_vlm && agentInheritedKey === "frontier" ? (
            <span className="badge badge-amber">inherits frontier</span>
          ) : null}
        </div>
        <div className="settings-grid">
          <ToggleField
            label="Inherit VLM"
            description="Agent endpoint reuses a configured VLM preset."
            checked={agent.inherit_vlm}
            onChange={(checked) =>
              updateDraft((current) => {
                const existing = normalizeAgent(current.agent);
                return {
                  ...current,
                  agent: {
                    ...existing,
                    inherit_vlm: checked,
                    inherit_vlm_mode: existing.inherit_vlm_mode ?? "active",
                    endpoint: checked ? {} : endpointDraft(existing.endpoint)
                  }
                };
              })
            }
          />
          {agent.inherit_vlm ? (
            <SelectField
              label="Inherit route"
              description="Use active VLM or pin the agent to a preset."
              value={agentInheritRoute}
              options={AGENT_INHERIT_ROUTES}
              optionLabels={AGENT_INHERIT_ROUTE_LABELS}
              onChange={(value) =>
                updateDraft((current) => ({
                  ...current,
                  agent: {
                    ...normalizeAgent(current.agent),
                    inherit_vlm: true,
                    inherit_vlm_mode: normalizeAgentInheritRoute(value),
                    endpoint: {}
                  }
                }))
              }
            />
          ) : null}
          <NumberField
            label="Max iterations"
            description="Maximum tool-call turns for one agent answer."
            value={agent.max_iterations}
            min={1}
            max={32}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                agent: { ...normalizeAgent(current.agent), max_iterations: value }
              }))
            }
          />
          <NumberField
            label="Agent max tokens"
            description="Generation budget for one agent response."
            value={agent.max_tokens}
            min={64}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                agent: { ...normalizeAgent(current.agent), max_tokens: value }
              }))
            }
          />
          <NumberField
            label="Agent temperature"
            description="Lower is more deterministic."
            value={agent.temperature}
            min={0}
            max={2}
            step={0.1}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                agent: { ...normalizeAgent(current.agent), temperature: value }
              }))
            }
          />
        </div>
        {agent.inherit_vlm ? (
          <div className="settings-note">
            Agent calls currently inherit {agentInheritLabel}:{" "}
            <strong>{agentInheritedEndpoint.model}</strong>.
          </div>
        ) : (
          <div className="settings-endpoints compact">
            <EndpointEditor
              title="Agent Endpoint"
              active
              endpoint={agentEndpoint}
              apiKeys={apiKeys}
              responseFormats={[]}
              showThinking={false}
              onChange={(patch) =>
                updateDraft((current) => {
                  const { generation, endpoint } = splitToolEndpointPatch(patch);
                  const existing = normalizeAgent(current.agent);
                  return {
                    ...current,
                    agent: {
                      ...existing,
                      ...generation,
                      endpoint: { ...existing.endpoint, ...endpoint }
                    }
                  };
                })
              }
            />
          </div>
        )}
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>Creative Analysis</h2>
            <p>Controls Synthetic Creative Review Panel and Debate. These are user-triggered LLM calls.</p>
          </div>
          {creativePanel.inherit_vlm && config.vlm.mode === "frontier" ? (
            <span className="badge badge-amber">inherits frontier</span>
          ) : null}
        </div>
        <div className="settings-grid">
          <ToggleField
            label="Inherit VLM"
            description="Creative Panel and Debate follow the selected VLM preset."
            checked={creativePanel.inherit_vlm}
            onChange={(checked) =>
              updateDraft((current) => {
                const existing = normalizeCreativePanel(current.creative_panel);
                return {
                  ...current,
                  creative_panel: {
                    ...existing,
                    inherit_vlm: checked,
                    endpoint: checked ? {} : endpointDraft(existing.endpoint)
                  }
                };
              })
            }
          />
          <NumberField
            label="Creative max tokens"
            description="Budget for each persona/debate generation."
            value={creativePanel.max_tokens}
            min={64}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                creative_panel: {
                  ...normalizeCreativePanel(current.creative_panel),
                  max_tokens: value
                }
              }))
            }
          />
          <NumberField
            label="Creative temperature"
            description="Lower is more deterministic."
            value={creativePanel.temperature}
            min={0}
            max={2}
            step={0.1}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                creative_panel: {
                  ...normalizeCreativePanel(current.creative_panel),
                  temperature: value
                }
              }))
            }
          />
        </div>
        {creativePanel.inherit_vlm ? (
          <div className="settings-note">
            Creative Panel and Debate currently use the active VLM route: <strong>{active.model}</strong>.
          </div>
        ) : (
          <div className="settings-endpoints compact">
            <EndpointEditor
              title="Creative Endpoint"
              active
              endpoint={creativeEndpoint}
              apiKeys={apiKeys}
              responseFormats={[]}
              showThinking={false}
              onChange={(patch) =>
                updateDraft((current) => {
                  const { generation, endpoint } = splitToolEndpointPatch(patch);
                  const existing = normalizeCreativePanel(current.creative_panel);
                  return {
                    ...current,
                    creative_panel: {
                      ...existing,
                      ...generation,
                      endpoint: { ...existing.endpoint, ...endpoint }
                    }
                  };
                })
              }
            />
          </div>
        )}
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

const TOOL_ENDPOINT_DEFAULTS: EndpointSettings = {
  endpoint: "http://127.0.0.1:1234/v1",
  model: "argus/vlm",
  api_key_env: null,
  timeout_s: 120,
  max_retries: 2,
  retry_delay_s: 2,
  temperature: 0.1,
  max_tokens: 1024,
  response_format: "json_object",
  stream: true
};

const DEFAULT_PROMPT_PROFILES = [
  {
    value: "auto",
    label: "Auto by route",
    description: "Use Frontier strict for Frontier routing and Standard elsewhere."
  },
  {
    value: "standard",
    label: "Standard",
    description: "Full guided verifier prompt for local and smaller models."
  },
  {
    value: "frontier_strict",
    label: "Frontier strict",
    description: "Compact evidence-only extractor prompt for strong models."
  }
];

const DEFAULT_AGENT_SETTINGS: SettingsConfig["agent"] = {
  inherit_vlm: true,
  inherit_vlm_mode: "active",
  endpoint: {},
  max_iterations: 8,
  list_max_rows: 50,
  sql_readonly_max_rows: 50,
  sql_statement_timeout_s: 5,
  temperature: 0.1,
  max_tokens: 1024
};

const AGENT_INHERIT_ROUTE_LABELS: Record<AgentInheritRoute, string> = {
  active: "Active VLM",
  local: "Local",
  remote: "Remote",
  frontier: "Frontier"
};

const DEFAULT_CREATIVE_PANEL_SETTINGS: SettingsConfig["creative_panel"] = {
  inherit_vlm: true,
  endpoint: {},
  temperature: 0.1,
  max_tokens: 8192
};

function normalizeAgent(value: Partial<SettingsConfig["agent"]> | undefined): SettingsConfig["agent"] {
  return {
    ...DEFAULT_AGENT_SETTINGS,
    ...(value ?? {}),
    inherit_vlm_mode: normalizeAgentInheritRoute(value?.inherit_vlm_mode),
    endpoint: value?.endpoint ?? {}
  };
}

function normalizeAgentInheritRoute(value: string | undefined): AgentInheritRoute {
  return AGENT_INHERIT_ROUTES.includes(value as AgentInheritRoute)
    ? (value as AgentInheritRoute)
    : "active";
}

function resolveAgentInheritedKey(
  config: SettingsConfig,
  route: AgentInheritRoute
): VlmEndpointKey {
  if (route !== "active") return route;
  return VLM_ENDPOINTS.includes(config.vlm.mode as VlmEndpointKey)
    ? (config.vlm.mode as VlmEndpointKey)
    : "local";
}

function inheritRouteLabel(route: AgentInheritRoute, resolvedKey: VlmEndpointKey) {
  if (route === "active") return `the active VLM route (${endpointTitle(resolvedKey)})`;
  return `the ${endpointTitle(route)} preset`;
}

function normalizeCreativePanel(
  value: Partial<SettingsConfig["creative_panel"]> | undefined
): SettingsConfig["creative_panel"] {
  return {
    ...DEFAULT_CREATIVE_PANEL_SETTINGS,
    ...(value ?? {}),
    endpoint: value?.endpoint ?? {}
  };
}

function toolEndpointForEditor(
  endpoint: Partial<EndpointSettings>,
  generation: Pick<EndpointSettings, "temperature" | "max_tokens">
): EndpointSettings {
  return {
    ...TOOL_ENDPOINT_DEFAULTS,
    ...endpoint,
    temperature: generation.temperature,
    max_tokens: generation.max_tokens
  };
}

function endpointDraft(endpoint: Partial<EndpointSettings>) {
  const full = toolEndpointForEditor(endpoint, {
    temperature: TOOL_ENDPOINT_DEFAULTS.temperature,
    max_tokens: TOOL_ENDPOINT_DEFAULTS.max_tokens
  });
  const { temperature: _temperature, max_tokens: _maxTokens, enable_thinking: _thinking, response_format: _format, ...draft } = full;
  return draft;
}

function splitToolEndpointPatch(patch: Partial<EndpointSettings>) {
  const {
    temperature,
    max_tokens,
    enable_thinking: _thinking,
    response_format: _format,
    ...endpoint
  } = patch;
  const generation: Partial<Pick<EndpointSettings, "temperature" | "max_tokens">> = {};
  if (typeof temperature === "number") generation.temperature = temperature;
  if (typeof max_tokens === "number") generation.max_tokens = max_tokens;
  return { generation, endpoint };
}
