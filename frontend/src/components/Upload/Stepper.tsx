import { CheckIcon, XIcon } from "../../lib/icons";
import type { JobRecord } from "../../lib/types";

const STEPS = [
  { key: "uploading", label: "Uploading", sub: "transferring file" },
  { key: "ingest", label: "Extracting frames", sub: "ffmpeg keyframes" },
  { key: "whisper", label: "Transcribing audio", sub: "whisper.cpp" },
  { key: "preprocess", label: "Preprocessing", sub: "blur / phash dedup" },
  { key: "dedup", label: "Dedup check", sub: "hash + phash" },
  { key: "ocr", label: "OCR", sub: "PaddleOCR + VL gating" },
  { key: "embed", label: "Embedding", sub: "MiniLM + SigLIP 2" },
  { key: "vlm", label: "VLM analysis", sub: "ARGUS classification" },
  { key: "finalize", label: "Finalizing", sub: "persist + FTS refresh" }
];

const STAGE_ALIASES: Record<string, string> = {
  embeddings: "embed",
  persist: "finalize",
};

function activeIndex(job?: JobRecord | null) {
  if (!job) return 0;
  const rawRootStage = (job.stage ?? "").split(":")[0].toLowerCase();
  const rootStage = STAGE_ALIASES[rawRootStage] ?? rawRootStage;
  const haystack = `${rootStage} ${job.state ?? ""} ${job.message ?? ""}`.toLowerCase();
  const idx = STEPS.findIndex((s) => rootStage === s.key || haystack.includes(s.key));
  if (idx >= 0) return idx;
  if (job.state === "completed") return STEPS.length;
  if (job.state === "failed" || job.state === "cancelled") {
    return Math.max(0, Math.floor((job.progress ?? 0) * STEPS.length));
  }
  return Math.min(STEPS.length - 1, Math.floor((job.progress ?? 0) * STEPS.length));
}

export function Stepper({ job }: { job?: JobRecord | null }) {
  const current = activeIndex(job);
  const failed = job?.state === "failed";
  const cancelled = job?.state === "cancelled";

  return (
    <div className="stepper">
      {STEPS.map((step, idx) => {
        const done = idx < current || job?.state === "completed";
        const active = !done && idx === current && !failed && !cancelled;
        const wasFailed = failed && idx === current;
        const wasCancelled = cancelled && idx === current;
        const cls = ["step"];
        if (done) cls.push("done");
        if (active) cls.push("active");
        if (wasFailed) cls.push("failed");
        if (wasCancelled) cls.push("cancelled");
        return (
          <div key={step.key} className={cls.join(" ")}>
            <div className="step-icon">
              {wasFailed ? (
                <XIcon size={12} />
              ) : wasCancelled ? (
                <XIcon size={12} />
              ) : done ? (
                <CheckIcon size={12} />
              ) : active ? (
                <span className="spinner" />
              ) : (
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: "var(--fg-quiet)"
                  }}
                />
              )}
            </div>
            <div>
              <div className="step-name">{step.label}</div>
              <div className="step-sub">{step.sub}</div>
            </div>
            <div className="step-time">
              {(active || wasFailed || wasCancelled) && job?.message ? job.message : done ? "ok" : ""}
            </div>
          </div>
        );
      })}
    </div>
  );
}
