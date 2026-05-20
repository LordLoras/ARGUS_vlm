import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { ApiKeySettings } from "../components/settings/ApiKeySettings";
import { CostCalculator } from "../components/settings/CostCalculator";
import { ModelSettings } from "../components/settings/ModelSettings";
import { OcrSettings } from "../components/settings/OcrSettings";
import { PipelineSettings } from "../components/settings/PipelineSettings";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { CheckIcon } from "../lib/icons";
import type { SettingsConfig } from "../lib/types";
import { cn } from "../lib/utils";

type SettingsTab = "models" | "cost" | "ocr" | "pipeline" | "keys";

const TABS: Array<{ id: SettingsTab; label: string }> = [
  { id: "models", label: "Models" },
  { id: "cost", label: "Cost" },
  { id: "ocr", label: "OCR" },
  { id: "pipeline", label: "Pipeline" },
  { id: "keys", label: "API Keys" }
];

export function Settings() {
  const queryClient = useQueryClient();
  const health = useApiHealth();
  const [tab, setTab] = useState<SettingsTab>("models");
  const [draft, setDraft] = useState<SettingsConfig | null>(null);

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings
  });

  useEffect(() => {
    if (settingsQuery.data) setDraft(cloneConfig(settingsQuery.data.config));
  }, [settingsQuery.data]);

  const updateMutation = useMutation({
    mutationFn: (config: SettingsConfig) => api.updateSettings(config),
    onSuccess: (snapshot) => {
      queryClient.setQueryData(["settings"], snapshot);
      setDraft(cloneConfig(snapshot.config));
    }
  });

  const apiKeys = settingsQuery.data?.api_keys ?? [];
  const isDirty = useMemo(() => {
    if (!draft || !settingsQuery.data) return false;
    return JSON.stringify(draft) !== JSON.stringify(settingsQuery.data.config);
  }, [draft, settingsQuery.data]);

  const updateDraft = (updater: (current: SettingsConfig) => SettingsConfig) => {
    setDraft((current) => (current ? updater(cloneConfig(current)) : current));
  };

  return (
    <>
      <Topbar crumbs={["System", "Settings"]} />
      <ApiOfflineBanner offline={health.isError} />
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Settings</h1>
            <p className="page-sub">
              Runtime model routing, ingest controls, and protected API key references.
            </p>
          </div>
          <div className="page-head-actions">
            <button
              className="btn"
              disabled={!isDirty || updateMutation.isPending}
              onClick={() => {
                if (settingsQuery.data) setDraft(cloneConfig(settingsQuery.data.config));
              }}
            >
              Reset
            </button>
            <button
              className="btn btn-primary"
              disabled={!draft || !isDirty || updateMutation.isPending}
              onClick={() => draft && updateMutation.mutate(draft)}
            >
              <CheckIcon size={12} />
              <span>{updateMutation.isPending ? "Saving" : "Save"}</span>
            </button>
          </div>
        </div>

        {!draft || !settingsQuery.data ? (
          <div style={{ padding: 28 }}>
            {settingsQuery.isError ? (
              <EmptyState title="Settings unavailable" hint={(settingsQuery.error as Error).message} />
            ) : (
              <EmptyState title="Loading settings" hint="Reading the active runtime configuration." />
            )}
          </div>
        ) : (
          <div className="settings-shell">
            <aside className="settings-rail" aria-label="Settings sections">
              {TABS.map((item) => (
                <button
                  key={item.id}
                  className={cn("settings-tab", tab === item.id && "active")}
                  onClick={() => setTab(item.id)}
                >
                  {item.label}
                </button>
              ))}
              <div className="settings-path">
                <span>Config</span>
                <strong>{settingsQuery.data.config_path}</strong>
              </div>
            </aside>

            <main className="settings-main">
              {updateMutation.error ? (
                <div className="settings-alert">{(updateMutation.error as Error).message}</div>
              ) : null}

              {tab === "models" ? (
                <ModelSettings
                  config={draft}
                  apiKeys={apiKeys}
                  modeOptions={settingsQuery.data.options.vlm_modes}
                  responseFormats={settingsQuery.data.options.response_formats}
                  updateDraft={updateDraft}
                />
              ) : tab === "cost" ? (
                <CostCalculator config={draft} />
              ) : tab === "ocr" ? (
                <OcrSettings config={draft} apiKeys={apiKeys} updateDraft={updateDraft} />
              ) : tab === "pipeline" ? (
                <PipelineSettings config={draft} updateDraft={updateDraft} />
              ) : (
                <ApiKeySettings
                  config={draft}
                  apiKeys={apiKeys}
                  dotenvPath={settingsQuery.data.dotenv_path}
                />
              )}
            </main>
          </div>
        )}
      </div>
    </>
  );
}

function cloneConfig(config: SettingsConfig): SettingsConfig {
  return JSON.parse(JSON.stringify(config)) as SettingsConfig;
}
