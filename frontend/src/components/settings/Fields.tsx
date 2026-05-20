import { cn } from "../../lib/utils";
import type { ApiKeyRecord, EndpointSettings } from "../../lib/types";

export function EndpointEditor({
  title,
  active,
  endpoint,
  apiKeys,
  responseFormats,
  showThinking = true,
  onChange
}: {
  title: string;
  active: boolean;
  endpoint: EndpointSettings;
  apiKeys: ApiKeyRecord[];
  responseFormats: string[];
  showThinking?: boolean;
  onChange: (patch: Partial<EndpointSettings>) => void;
}) {
  const keyNames = apiKeys.map((item) => item.name);
  if (endpoint.api_key_env && !keyNames.includes(endpoint.api_key_env)) keyNames.push(endpoint.api_key_env);

  return (
    <div className={cn("settings-endpoint", active && "active")}>
      <div className="settings-endpoint-head">
        <strong>{title}</strong>
        {active ? <span className="badge badge-emerald">active</span> : null}
      </div>
      <div className="settings-grid single">
        <TextField
          label="Endpoint"
          description="OpenAI-compatible base URL."
          value={endpoint.endpoint}
          onChange={(value) => onChange({ endpoint: value })}
        />
        <TextField
          label="Model"
          description="Provider model id."
          value={endpoint.model}
          onChange={(value) => onChange({ model: value })}
        />
        <SelectField
          label="API key variable"
          description="Secret value is stored separately."
          value={endpoint.api_key_env ?? ""}
          options={["", ...keyNames.sort()]}
          optionLabels={{ "": "No API key" }}
          onChange={(value) => onChange({ api_key_env: value || null })}
        />
        <div className="settings-number-row">
          <NumberField
            label="Timeout"
            description="Seconds."
            value={endpoint.timeout_s}
            min={0}
            onChange={(value) => onChange({ timeout_s: value })}
          />
          <NumberField
            label="Retries"
            description="Attempts."
            value={endpoint.max_retries}
            min={0}
            onChange={(value) => onChange({ max_retries: value })}
          />
        </div>
        <div className="settings-number-row">
          <NumberField
            label="Temperature"
            description="0-2."
            value={endpoint.temperature}
            min={0}
            max={2}
            step={0.1}
            onChange={(value) => onChange({ temperature: value })}
          />
          <NumberField
            label="Max tokens"
            description="Generation budget."
            value={endpoint.max_tokens}
            min={64}
            onChange={(value) => onChange({ max_tokens: value })}
          />
        </div>
        {responseFormats.length ? (
          <SelectField
            label="Response format"
            description="Use schema for capable frontier/remote models."
            value={endpoint.response_format ?? "json_object"}
            options={responseFormats}
            onChange={(value) => onChange({ response_format: value })}
          />
        ) : null}
        <div className="settings-inline-toggles">
          <ToggleField
            label="Stream"
            description="Use streaming HTTP responses."
            checked={endpoint.stream}
            onChange={(checked) => onChange({ stream: checked })}
          />
          {showThinking ? (
            <ToggleField
              label="Thinking"
              description="Only for models that still emit valid JSON."
              checked={Boolean(endpoint.enable_thinking)}
              onChange={(checked) => onChange({ enable_thinking: checked })}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function TextField({
  label,
  description,
  value,
  type = "text",
  onChange
}: {
  label: string;
  description: string;
  value: string;
  type?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      <input className="input" type={type} value={value ?? ""} onChange={(event) => onChange(event.target.value)} />
      <small>{description}</small>
    </label>
  );
}

export function NumberField({
  label,
  description,
  value,
  min,
  max,
  step = 1,
  onChange
}: {
  label: string;
  description: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      <input
        className="input"
        type="number"
        min={min}
        max={max}
        step={step}
        value={Number.isFinite(value) ? value : 0}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <small>{description}</small>
    </label>
  );
}

export function SelectField({
  label,
  description,
  value,
  options,
  optionLabels,
  onChange
}: {
  label: string;
  description: string;
  value: string;
  options: string[];
  optionLabels?: Record<string, string>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      <select className="input" value={value ?? ""} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {optionLabels?.[option] ?? option}
          </option>
        ))}
      </select>
      <small>{description}</small>
    </label>
  );
}

export function ToggleField({
  label,
  description,
  checked,
  onChange
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <button className="settings-toggle" type="button" onClick={() => onChange(!checked)}>
      <span className={cn("switch", checked && "on")} />
      <span>
        <strong>{label}</strong>
        <small>{description}</small>
      </span>
    </button>
  );
}

export function endpointTitle(mode: string) {
  if (mode === "local") return "Local";
  if (mode === "remote") return "Remote";
  if (mode === "frontier") return "Frontier";
  return mode;
}
