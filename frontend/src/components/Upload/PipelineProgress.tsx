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
  return (
    <div className="upload-card">
      <div className="pipeline-head">
        <span className="filename">{filename}</span>
        <span className="ad-id">{adId}</span>
        {jobId ? <span className="ad-id" style={{ color: "var(--accent-2)" }}>{jobId}</span> : null}
        <span className="ad-id">{(elapsedMs / 1000).toFixed(1)}s</span>
        <div className="actions">
          <button className="btn btn-sm" disabled={!jobId} onClick={onCancel}>
            Cancel
          </button>
        </div>
      </div>
      <div className="progress-bar">
        <span style={{ width: `${progress * 100}%` }} />
      </div>
      <Stepper job={job} />
      <LiveLog lines={logLines} />
    </div>
  );
}
