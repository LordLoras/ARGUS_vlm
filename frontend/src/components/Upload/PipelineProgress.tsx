import type { JobRecord } from "../../lib/types";
import { LiveLog, type LogLine } from "./LiveLog";
import { Stepper } from "./Stepper";

const STAGE_LABELS: Record<string, string> = {
  upload: "Uploading file",
  uploading: "Uploading file",
  queued: "Waiting for worker",
  ingest: "Extracting frames & audio",
  whisper: "Transcribing with Whisper",
  preprocess: "Preprocessing frames",
  dedup: "Checking duplicates",
  ocr: "Running OCR",
  paddlevl: "Checking hard OCR frames",
  glm_ocr: "Checking GLM-OCR frames",
  rules: "Running rules",
  vlm: "VLM classification",
  embed: "Generating embeddings",
  embeddings: "Generating embeddings",
  finalize: "Persisting results",
  persist: "Persisting results",
  completed: "Pipeline complete",
  cancelled: "Pipeline cancelled",
  failed: "Pipeline failed",
};

export function PipelineProgress({
  filename,
  adId,
  jobId,
  job,
  elapsedMs,
  logLines,
  onCancel,
  onClear
}: {
  filename: string;
  adId: string;
  jobId: string | null;
  job?: JobRecord | null;
  elapsedMs: number;
  logLines: LogLine[];
  onCancel: () => void;
  onClear: () => void;
}) {
  const progress = Math.max(0, Math.min(1, job?.progress ?? 0));
  const stageRoot = job?.stage?.split(":")[0].toLowerCase() || "";
  const stage = STAGE_LABELS[stageRoot] || job?.stage || job?.message || job?.state || "";
  const terminal = job?.state === "failed" || job?.state === "cancelled";
  const failed = job?.state === "failed";
  const statusText = failed
    ? `Fatal error: ${job?.error || job?.message || "pipeline stopped"}`
    : job?.state === "cancelled"
      ? "Job cancelled. Processing has stopped."
      : null;
  return (
    <div className={`pp-card ${failed ? "failed" : job?.state === "cancelled" ? "cancelled" : ""}`}>
      <div className="pp-head">
        <div className="pp-head-left">
          <span className="pp-filename">{filename}</span>
          <span className="pp-id">{adId}</span>
          {jobId ? <span className="pp-id dim">{jobId}</span> : null}
        </div>
        <div className="pp-head-right">
          <span className="pp-elapsed">{(elapsedMs / 1000).toFixed(1)}s</span>
          {terminal ? (
            <button className="btn btn-sm" onClick={onClear}>
              Clear
            </button>
          ) : (
            <button className="btn btn-sm" disabled={!jobId} onClick={onCancel}>
              Cancel
            </button>
          )}
        </div>
      </div>
      {statusText ? (
        <div className={`pp-status ${failed ? "error" : "warn"}`}>{statusText}</div>
      ) : null}
      <div className="pp-progress">
        <div className="pp-progress-bar" style={{ width: `${Math.max(progress * 100, 2)}%` }} />
      </div>
      <div className="pp-stage-label">{stage || "queued"}</div>
      <Stepper job={job} />
      <LiveLog lines={logLines} />
    </div>
  );
}
