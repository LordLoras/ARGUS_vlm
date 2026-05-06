import { useMutation, useQuery } from "@tanstack/react-query";
import { FileVideo, UploadCloud, X } from "lucide-react";
import { useMemo, useState } from "react";

import { PipelineProgress } from "../components/Upload/PipelineProgress";
import { ResultPanel } from "../components/Upload/ResultPanel";
import { Button } from "../components/ui/Button";
import { Card, CardTitle } from "../components/ui/Card";
import { api } from "../lib/api-client";
import { useJobEvents } from "../hooks/useJobEvents";

export function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [adId, setAdId] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJobEvents(jobId);

  const uploadMutation = useMutation({
    mutationFn: (selected: File) => api.uploadAd(selected),
    onSuccess: (result) => {
      setAdId(result.ad_id);
      setJobId(result.job_id);
    }
  });

  const isDone = job?.state === "completed" || (adId && !jobId);
  const detailQuery = useQuery({
    queryKey: ["upload-detail", adId],
    queryFn: () => api.getAd(adId ?? ""),
    enabled: Boolean(isDone && adId)
  });
  const framesQuery = useQuery({
    queryKey: ["upload-frames", adId],
    queryFn: () => api.getFrames(adId ?? ""),
    enabled: Boolean(isDone && adId)
  });
  const relatedQuery = useQuery({
    queryKey: ["upload-related", adId],
    queryFn: () => api.getSimilar(adId ?? ""),
    enabled: Boolean(isDone && adId)
  });

  const sizeText = useMemo(() => {
    if (!file) return "";
    return `${(file.size / (1024 * 1024)).toFixed(1)} MB`;
  }, [file]);

  const reset = () => {
    setFile(null);
    setAdId(null);
    setJobId(null);
    uploadMutation.reset();
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Upload + Classification</h1>
        <p className="mt-1 text-sm text-muted-foreground">Drop a local ad clip and watch the worker progress through the pipeline.</p>
      </div>

      {!adId && (
        <Card className="text-center">
          <label className="block cursor-pointer rounded-lg border border-dashed border-violet-400/50 bg-violet-500/5 p-12 transition hover:border-violet-300 hover:bg-violet-500/10">
            <UploadCloud className="mx-auto h-12 w-12 text-violet-200" />
            <div className="mt-4 text-xl font-semibold">Drop a video here</div>
            <div className="mt-2 text-sm text-muted-foreground">or click to browse · MP4 · MOV · WebM · up to 200 MB</div>
            <input
              type="file"
              accept="video/mp4,video/quicktime,video/webm"
              className="hidden"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>

          {file && (
            <div className="mt-5 rounded-lg border border-border bg-muted p-4 text-left">
              <div className="flex items-center gap-3">
                <FileVideo className="h-5 w-5 text-violet-200" />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{file.name}</div>
                  <div className="text-xs text-muted-foreground">{file.type || "video"} · {sizeText}</div>
                </div>
                <Button variant="ghost" onClick={() => setFile(null)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <Button className="mt-4 w-full" variant="primary" disabled={uploadMutation.isPending} onClick={() => uploadMutation.mutate(file)}>
                Start classification
              </Button>
            </div>
          )}

          {uploadMutation.isError && <p className="mt-4 text-sm text-red-300">{String(uploadMutation.error.message)}</p>}
        </Card>
      )}

      {adId && !isDone && (
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <CardTitle>{file?.name ?? "Uploaded video"}</CardTitle>
              <div className="mt-1 font-mono text-xs text-muted-foreground">{adId}</div>
            </div>
            {jobId && (
              <Button variant="secondary" onClick={() => api.cancelJob(jobId)}>
                Cancel
              </Button>
            )}
          </div>
          <PipelineProgress job={job} />
          {job?.state === "failed" && (
            <div className="mt-4 rounded-md border border-red-900/60 bg-red-950/40 p-3 text-sm text-red-100">
              {job.error || job.message || "Pipeline failed."}
            </div>
          )}
        </Card>
      )}

      {isDone && detailQuery.data && (
        <ResultPanel
          detail={detailQuery.data}
          frames={framesQuery.data?.items ?? []}
          related={relatedQuery.data}
          onReset={reset}
        />
      )}
    </div>
  );
}
