import { Check, Circle, Loader2, X } from "lucide-react";

import type { JobRecord } from "../../lib/types";
import { Progress } from "../ui/Progress";

const steps = [
  ["queued", "Uploading"],
  ["ingest", "Extracting frames"],
  ["whisper", "Transcribing audio"],
  ["preprocess", "Preprocessing"],
  ["dedup", "Dedup check"],
  ["ocr", "OCR"],
  ["embeddings", "Embedding"],
  ["vlm", "VLM analysis"],
  ["persist", "Finalizing"],
  ["completed", "Done"]
] as const;

function activeIndex(job?: JobRecord | null) {
  if (!job) return 0;
  const message = `${job.state} ${job.message ?? ""}`.toLowerCase();
  const found = steps.findIndex(([key]) => message.includes(key));
  if (found >= 0) return found;
  if (job.state === "completed") return steps.length - 1;
  if (job.state === "failed" || job.state === "cancelled") return steps.length - 1;
  return Math.min(steps.length - 1, Math.floor((job.progress ?? 0) * steps.length));
}

export function PipelineProgress({ job }: { job?: JobRecord | null }) {
  const current = activeIndex(job);
  const failed = job?.state === "failed";

  return (
    <div>
      <Progress value={job?.progress ?? 0} />
      <div className="mt-5 space-y-3">
        {steps.map(([, label], index) => {
          const done = index < current || job?.state === "completed";
          const active = index === current && !done && !failed;
          return (
            <div key={label} className="flex items-center gap-3 rounded-md bg-muted/55 px-3 py-2">
              <div className="text-violet-200">
                {failed && index === current ? (
                  <X className="h-4 w-4 text-red-300" />
                ) : done ? (
                  <Check className="h-4 w-4" />
                ) : active ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
              <div className="font-mono text-sm">{label}</div>
              {active && <div className="ml-auto text-xs text-muted-foreground">{job?.message}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
