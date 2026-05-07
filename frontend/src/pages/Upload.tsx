import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { Dropzone } from "../components/Upload/Dropzone";
import { PipelineProgress } from "../components/Upload/PipelineProgress";
import type { LogLine } from "../components/Upload/LiveLog";
import { ResultPanel } from "../components/Upload/ResultPanel";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { useJobEvents } from "../hooks/useJobEvents";
import { api } from "../lib/api-client";
import { CloseIcon, UploadIcon } from "../lib/icons";

export function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [adId, setAdId] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<LogLine[]>([]);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const job = useJobEvents(jobId);
  const health = useApiHealth();
  const lastSig = useRef<string>("");

  const uploadMutation = useMutation({
    mutationFn: (selected: File) => api.uploadAd(selected),
    onSuccess: (result) => {
      setAdId(result.ad_id);
      setJobId(result.job_id ?? null);
      setStartedAt(Date.now());
      setLogLines([
        timestampedLog("info", `accepted ${result.ad_id}`),
        ...(result.duplicate_of
          ? [timestampedLog("warn", `duplicate of ${result.duplicate_of} — skipping pipeline`)]
          : [])
      ]);
    },
    onError: (err) => {
      setLogLines((lines) => [...lines, timestampedLog("warn", `upload failed: ${(err as Error).message}`)]);
    }
  });

  useEffect(() => {
    const handle = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(handle);
  }, []);

  useEffect(() => {
    if (!job) return;
    const sig = `${job.state}|${job.progress ?? ""}|${job.message ?? ""}`;
    if (sig === lastSig.current) return;
    lastSig.current = sig;
    const level: LogLine["level"] = job.state === "failed" ? "warn" : job.state === "completed" ? "ok" : "info";
    const msg = job.message ?? job.state ?? "(no message)";
    setLogLines((lines) => [...lines, timestampedLog(level, `${job.state}: ${msg}`)]);
  }, [job]);

  const isDone = (job?.state === "completed") || (adId && jobId === null);
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

  const sizeText = useMemo(() => (file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB` : ""), [file]);
  const elapsed = startedAt ? now - startedAt : 0;

  const reset = () => {
    setFile(null);
    setAdId(null);
    setJobId(null);
    setLogLines([]);
    setStartedAt(null);
    uploadMutation.reset();
  };

  const cancel = () => {
    if (jobId) void api.cancelJob(jobId);
  };

  return (
    <>
      <Topbar crumbs={["Workspace", "Upload"]} />
      <ApiOfflineBanner offline={health.isError} />

      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Upload</h1>
            <p className="page-sub">Drop a clip and watch the local pipeline classify it.</p>
          </div>
        </div>

        <div className="upload-stage">
          {!adId && !uploadMutation.isPending ? (
            <>
              <Dropzone
                onFile={(f) => {
                  setFile(f);
                  uploadMutation.mutate(f);
                }}
              />
              {file ? (
                <div className="upload-card">
                  <div className="upload-card-head">
                    <span className="step-num">2</span>
                    <span>Confirm and start</span>
                  </div>
                  <div
                    style={{
                      padding: 16,
                      display: "flex",
                      gap: 12,
                      alignItems: "center"
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600 }}>{file.name}</div>
                      <div className="mono" style={{ fontSize: 11, color: "var(--fg-mute)" }}>
                        {file.type || "video"} · {sizeText}
                      </div>
                    </div>
                    <button className="btn btn-icon" onClick={() => setFile(null)} title="Clear">
                      <CloseIcon size={12} />
                    </button>
                    <button
                      className="btn btn-primary"
                      disabled={uploadMutation.isPending}
                      onClick={() => uploadMutation.mutate(file)}
                    >
                      <UploadIcon size={12} />
                      <span>Start classification</span>
                    </button>
                  </div>
                </div>
              ) : null}
              {uploadMutation.isError ? (
                <div className="upload-card" style={{ borderColor: "var(--rose)", color: "var(--rose)" }}>
                  <div style={{ padding: 14 }}>{(uploadMutation.error as Error).message}</div>
                </div>
              ) : null}
            </>
          ) : null}

          {(uploadMutation.isPending || (adId && !isDone)) && adId ? (
            <PipelineProgress
              filename={file?.name ?? "uploaded clip"}
              adId={adId}
              jobId={jobId}
              job={job}
              elapsedMs={elapsed}
              logLines={logLines}
              onCancel={cancel}
            />
          ) : null}

          {uploadMutation.isPending && !adId ? (
            <div className="upload-card">
              <div className="pipeline-head">
                <span className="filename">{file?.name ?? "uploading…"}</span>
                <span className="ad-id">queued</span>
              </div>
              <div className="progress-bar">
                <span style={{ width: "8%" }} />
              </div>
            </div>
          ) : null}

          {isDone && detailQuery.data ? (
            <ResultPanel
              detail={detailQuery.data}
              frames={framesQuery.data?.items ?? []}
              related={relatedQuery.data}
              elapsedMs={elapsed}
              onReset={reset}
            />
          ) : null}

          {isDone && detailQuery.isLoading ? (
            <div className="obs-empty" style={{ padding: 24 }}>Loading result…</div>
          ) : null}
        </div>
      </div>
    </>
  );
}

function timestampedLog(level: LogLine["level"], message: string): LogLine {
  const now = new Date();
  const pad = (n: number) => n.toString().padStart(2, "0");
  return {
    ts: `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`,
    level,
    message
  };
}
