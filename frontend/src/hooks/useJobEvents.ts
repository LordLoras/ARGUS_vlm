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
          ad_id: prev?.ad_id ?? null,
          state: event.state,
          progress: event.progress,
          message: event.message,
          error: event.error
        }));
      }
    });
    return () => {
      cancelled = true;
      cleanup();
    };
  }, [jobId]);

  return job;
}
