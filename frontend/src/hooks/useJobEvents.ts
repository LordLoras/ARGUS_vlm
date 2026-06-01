import { useEffect, useState } from "react";

import { api, streamJobEvents } from "../lib/api-client";
import type { JobRecord } from "../lib/types";

export function useJobEvents(jobId: string | null) {
  const [job, setJob] = useState<JobRecord | null>(null);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return undefined;
    }
    let cancelled = false;
    void api.getJob(jobId).then(
      (current) => {
        if (!cancelled) setJob(current);
      },
      () => {
        if (!cancelled) setJob(null);
      }
    );
    const cleanup = streamJobEvents(jobId, (event) => {
      if (event.type === "job") {
        setJob((prev) => ({
          id: event.job_id,
          ad_id: event.ad_id ?? prev?.ad_id ?? null,
          state: event.state,
          progress: event.progress,
          stage: event.stage,
          message: event.message,
          error: event.error,
          started_at: event.started_at ?? prev?.started_at ?? null,
          finished_at: event.finished_at ?? prev?.finished_at ?? null
        }));
      } else if (event.type === "error") {
        setJob((prev) =>
          prev
            ? {
                ...prev,
                state: "failed",
                stage: "event-stream",
                message: "event stream error",
                error: event.message
              }
            : null
        );
      }
    });
    return () => {
      cancelled = true;
      cleanup();
    };
  }, [jobId]);

  return job;
}
