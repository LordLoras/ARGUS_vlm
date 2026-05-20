import { NumberField, SelectField, TextField, ToggleField } from "./Fields";
import type { UpdateSettingsDraft } from "./types";
import type { SettingsConfig } from "../../lib/types";

export function PipelineSettings({
  config,
  updateDraft
}: {
  config: SettingsConfig;
  updateDraft: UpdateSettingsDraft;
}) {
  return (
    <div className="settings-stack">
      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>Ingest</h2>
            <p>Frame cadence, upload limits, and local process paths.</p>
          </div>
        </div>
        <div className="settings-grid">
          <NumberField
            label="Frame interval"
            description="Milliseconds between sampled frames."
            value={config.ingest.frame_interval_ms}
            min={1}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                ingest: { ...current.ingest, frame_interval_ms: value }
              }))
            }
          />
          <NumberField
            label="Audio sample rate"
            description="Mono audio sample rate for transcript extraction."
            value={config.ingest.audio_sample_rate}
            min={8000}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                ingest: { ...current.ingest, audio_sample_rate: value }
              }))
            }
          />
          <NumberField
            label="Upload limit"
            description="Maximum uploaded video bytes."
            value={config.api.upload.max_bytes}
            min={1}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                api: {
                  ...current.api,
                  upload: { ...current.api.upload, max_bytes: value }
                }
              }))
            }
          />
          <NumberField
            label="Rule window"
            description="Transcript alignment window in milliseconds."
            value={config.rules.alignment_window_ms}
            min={0}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                rules: { ...current.rules, alignment_window_ms: value }
              }))
            }
          />
          <TextField
            label="ffmpeg"
            description="Command name or absolute executable path."
            value={config.ingest.ffmpeg_path}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                ingest: { ...current.ingest, ffmpeg_path: value }
              }))
            }
          />
          <TextField
            label="ffprobe"
            description="Command name or absolute executable path."
            value={config.ingest.ffprobe_path}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                ingest: { ...current.ingest, ffprobe_path: value }
              }))
            }
          />
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section-head">
          <div>
            <h2>Embeddings and Worker</h2>
            <p>Vector dimensions must match the configured embedding models and local SQLite-vec store.</p>
          </div>
        </div>
        <div className="settings-grid">
          <ToggleField
            label="Visual embeddings"
            description="Index SigLIP image vectors for visual search."
            checked={config.image_embedder.enabled}
            onChange={(checked) =>
              updateDraft((current) => ({
                ...current,
                image_embedder: { ...current.image_embedder, enabled: checked }
              }))
            }
          />
          <SelectField
            label="Text device"
            description="Torch device for text embeddings."
            value={config.text_embedder.device}
            options={["cpu", "cuda"]}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                text_embedder: { ...current.text_embedder, device: value }
              }))
            }
          />
          <SelectField
            label="Visual device"
            description="Torch device for image embeddings."
            value={config.image_embedder.device}
            options={["cpu", "cuda"]}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                image_embedder: { ...current.image_embedder, device: value }
              }))
            }
          />
          <NumberField
            label="Worker poll"
            description="Milliseconds between queue checks."
            value={config.worker.poll_interval_ms}
            min={50}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                worker: { ...current.worker, poll_interval_ms: value }
              }))
            }
          />
          <NumberField
            label="Worker concurrency"
            description="Keep at 1 for local GPU/VLM stability."
            value={config.worker.concurrency}
            min={1}
            onChange={(value) =>
              updateDraft((current) => ({
                ...current,
                worker: { ...current.worker, concurrency: value }
              }))
            }
          />
          <ToggleField
            label="Brand profiles"
            description="User-triggered Wikimedia enrichment."
            checked={config.brand_profiles.enabled}
            onChange={(checked) =>
              updateDraft((current) => ({
                ...current,
                brand_profiles: { ...current.brand_profiles, enabled: checked }
              }))
            }
          />
        </div>
      </section>
    </div>
  );
}
