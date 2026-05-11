import type { JobRecord } from "../../lib/types";
import { LiveLog, type LogLine } from "./LiveLog";
import { Stepper } from "./Stepper";

export function PipelineProgress({
  filename,
  adId,
  jobId,
  job,
  elapsedMs,
  logLines,
  onCancel
}: {
  filename: string;
  adId: string;
  jobId: string | null;
  job?: JobRecord | null;
  elapsedMs: number;
  logLines: LogLine[];
  onCancel: () => void;
}) {
  const progress = Math.max(0, Math.min(1, job?.progress ?? 0));
  const stage = job?.message || job?.state || "";
  return (
    <div className="pp-card">
      <div className="pp-head">
        <div className="pp-head-left">
          <span className="pp-filename">{filename}</span>
          <span className="pp-id">{adId}</span>
          {jobId ? <span className="pp-id dim">{jobId}</span> : null}
        </div>
        <div className="pp-head-right">
          <span className="pp-elapsed">{(elapsedMs / 1000).toFixed(1)}s</span>
          <button className="btn btn-sm" disabled={!jobId} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
      <div className="pp-progress">
        <div className="pp-progress-bar" style={{ width: `${Math.max(progress * 100, 2)}%` }} />
      </div>
      <div className="pp-stage-label">{stage || "queued"}</div>
      <Stepper job={job} />
      <LiveLog lines={logLines} />
    </div>
  );
}
