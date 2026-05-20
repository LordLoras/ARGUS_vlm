import { EndpointEditor, NumberField, SelectField, TextField, ToggleField, endpointTitle } from "./Fields";
import { GLM_ENDPOINTS, type UpdateSettingsDraft } from "./types";
import type { ApiKeyRecord, SettingsConfig } from "../../lib/types";
import { cn } from "../../lib/utils";

export function OcrSettings({
  config,
  apiKeys,
  updateDraft
}: {
  config: SettingsConfig;
  apiKeys: ApiKeyRecord[];
  updateDraft: UpdateSettingsDraft;
}) {
  return (
    <div className="settings-stack">
      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>PaddleOCR</h2>
            <p>Raw visible-text extraction used for evidence, rules, and indexing.</p>
          </div>
        </div>
        <div className="settings-grid">
          <ToggleField
            label="Enabled"
            description="Run raw OCR before VLM verification."
            checked={config.ocr.enabled}
            onChange={(checked) =>
              updateDraft((current) => ({ ...current, ocr: { ...current.ocr, enabled: checked } }))
            }
          />
          <SelectField
            label="Device"
            description="CPU is the stable local default."
            value={config.ocr.device}
            options={["cpu", "gpu", "cuda"]}
            onChange={(value) =>
              updateDraft((current) => ({ ...current, ocr: { ...current.ocr, device: value } }))
            }
          />
          <TextField
            label="Language"
            description="Paddle language code."
            value={config.ocr.lang}
            onChange={(value) =>
              updateDraft((current) => ({ ...current, ocr: { ...current.ocr, lang: value } }))
            }
          />
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>GLM-OCR</h2>
            <p>Optional OpenAI-compatible document OCR for dense text frames.</p>
          </div>
          <span className={cn("badge", config.glm_ocr.enabled ? "badge-emerald" : "badge-mono")}>
            {config.glm_ocr.enabled ? "enabled" : "disabled"}
          </span>
        </div>
        <div className="settings-grid">
          <ToggleField
            label="Enabled"
            description="Run the document/OCR-VL pass on gated frames."
            checked={config.glm_ocr.enabled}
            onChange={(checked) =>
              updateDraft((current) => ({
                ...current,
                glm_ocr: { ...current.glm_ocr, enabled: checked }
              }))
            }
          />
          <SelectField
            label="Mode"
            description="Endpoint preset used by GLM-OCR."
            value={config.glm_ocr.mode}
            options={["local", "remote"]}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                glm_ocr: { ...current.glm_ocr, mode: value }
              }))
            }
          />
          <NumberField
            label="Image max dim"
            description="Input image size for OCR-VL frames."
            value={config.glm_ocr.image_max_dim}
            min={128}
            max={2048}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                glm_ocr: { ...current.glm_ocr, image_max_dim: value }
              }))
            }
          />
          <NumberField
            label="Max frames"
            description="Per-ad cap for OCR-VL calls."
            value={config.glm_ocr.max_frames_per_ad}
            min={1}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                glm_ocr: { ...current.glm_ocr, max_frames_per_ad: value }
              }))
            }
          />
          <ToggleField
            label="Search text"
            description="Include GLM-OCR text in search indexing."
            checked={config.glm_ocr.include_in_search}
            onChange={(checked) =>
              updateDraft((current) => ({
                ...current,
                glm_ocr: { ...current.glm_ocr, include_in_search: checked }
              }))
            }
          />
          <ToggleField
            label="VLM bundle"
            description="Feed GLM-OCR text to the classifier."
            checked={config.glm_ocr.include_in_vlm_bundle}
            onChange={(checked) =>
              updateDraft((current) => ({
                ...current,
                glm_ocr: { ...current.glm_ocr, include_in_vlm_bundle: checked }
              }))
            }
          />
        </div>

        <div className="settings-endpoints compact">
          {GLM_ENDPOINTS.map((mode) => (
            <EndpointEditor
              key={mode}
              title={`GLM ${endpointTitle(mode)}`}
              active={config.glm_ocr.mode === mode}
              endpoint={config.glm_ocr[mode]}
              apiKeys={apiKeys}
              responseFormats={[]}
              showThinking={false}
              onChange={(patch) =>
                updateDraft((current) => ({
                  ...current,
                  glm_ocr: {
                    ...current.glm_ocr,
                    [mode]: { ...current.glm_ocr[mode], ...patch }
                  }
                }))
              }
            />
          ))}
        </div>
      </section>
    </div>
  );
}
