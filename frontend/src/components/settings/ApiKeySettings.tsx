import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { EmptyState } from "../shared/EmptyState";
import { TextField } from "./Fields";
import { GLM_ENDPOINTS, VLM_ENDPOINTS } from "./types";
import { api } from "../../lib/api-client";
import { ShieldIcon, TrashIcon } from "../../lib/icons";
import type { ApiKeyRecord, SettingsConfig } from "../../lib/types";
import { cn } from "../../lib/utils";

export function ApiKeySettings({
  config,
  apiKeys,
  dotenvPath
}: {
  config: SettingsConfig;
  apiKeys: ApiKeyRecord[];
  dotenvPath: string;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("OPENROUTER_API_KEY");
  const [value, setValue] = useState("");

  const createMutation = useMutation({
    mutationFn: () => api.addApiKey({ name, value }),
    onSuccess: (snapshot) => {
      queryClient.setQueryData(["settings"], snapshot);
      setValue("");
    }
  });
  const deleteMutation = useMutation({
    mutationFn: (keyName: string) => api.deleteApiKey(keyName),
    onSuccess: (snapshot) => queryClient.setQueryData(["settings"], snapshot)
  });

  const configured = new Set<string>();
  VLM_ENDPOINTS.forEach((mode) => {
    if (config.vlm[mode].api_key_env) configured.add(config.vlm[mode].api_key_env as string);
  });
  GLM_ENDPOINTS.forEach((mode) => {
    if (config.glm_ocr[mode].api_key_env) configured.add(config.glm_ocr[mode].api_key_env as string);
  });

  return (
    <div className="settings-stack">
      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>Protected API Keys</h2>
            <p>Key values are written locally and never returned by the API after save.</p>
          </div>
          <span className="badge badge-mono">{dotenvPath}</span>
        </div>

        <div className="settings-secret-form">
          <TextField
            label="Variable name"
            description="Use uppercase letters, numbers, and underscores."
            value={name}
            onChange={(next) => setName(next.toUpperCase().replace(/[^A-Z0-9_]/g, ""))}
          />
          <TextField
            label="API key"
            description="Stored locally; never echoed back."
            type="password"
            value={value}
            onChange={setValue}
          />
          <button
            className="btn btn-primary settings-secret-save"
            disabled={!name || !value || createMutation.isPending}
            onClick={() => createMutation.mutate()}
          >
            <ShieldIcon size={12} />
            <span>{createMutation.isPending ? "Saving" : "Add key"}</span>
          </button>
        </div>
        {createMutation.error ? (
          <div className="settings-alert">{(createMutation.error as Error).message}</div>
        ) : null}
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>Key References</h2>
            <p>Choose these variable names in model endpoint presets.</p>
          </div>
        </div>
        <div className="settings-key-list">
          {apiKeys.map((key) => (
            <div key={key.name} className="settings-key-row">
              <div>
                <strong>{key.name}</strong>
                <span>
                  {key.sources.length ? key.sources.join(" + ") : "not available"}
                  {key.used_by.length ? ` / ${key.used_by.join(", ")}` : ""}
                </span>
              </div>
              <div className="settings-key-actions">
                <span className={cn("badge", key.available ? "badge-emerald" : "badge-rose")}>
                  {key.available ? "ready" : "missing"}
                </span>
                <button
                  className="btn btn-sm btn-danger"
                  disabled={!key.managed || deleteMutation.isPending}
                  onClick={() => {
                    if (window.confirm(`Remove ${key.name} from local secrets?`)) {
                      deleteMutation.mutate(key.name);
                    }
                  }}
                  title={key.managed ? "Remove local secret" : "Only env.local keys can be removed here"}
                >
                  <TrashIcon size={11} />
                  <span>Remove</span>
                </button>
              </div>
            </div>
          ))}
          {apiKeys.length === 0 ? (
            <EmptyState title="No key references" hint="Add a key, then select its variable name in an endpoint preset." />
          ) : null}
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>Configured Variables</h2>
            <p>Endpoint presets currently reference these names.</p>
          </div>
        </div>
        <div className="pill-row">
          {[...configured].sort().map((item) => (
            <span key={item} className="obs-tag">
              {item}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
