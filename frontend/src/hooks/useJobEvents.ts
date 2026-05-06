import { useEffect, useState } from "react";

import { streamJobEvents } from "../lib/api-client";
import type { JobRecord } from "../lib/types";

export function useJobEvents(jobId: string | null) {
  const [job, setJob] = useState<JobRecord | null>(null);

  useEffect(() => {
    if (!jobId) return undefined;
    const cleanup = streamJobEvents(jobId, (event) => {
      if (event.type === "job") {
        setJob({
          id: event.job_id,
          ad_id: "",
          state: event.state,
          progress: event.progress,
          message: event.message,
          error: event.error
        });
      }
    });
    return cleanup;
  }, [jobId]);

  return job;
}
