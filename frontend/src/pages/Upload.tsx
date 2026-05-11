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

const STAGE_LABELS: Record<string, string> = {
  upload: "Uploading file",
  ingest: "Extracting frames & audio",
  whisper: "Transcribing with Whisper",
  preprocess: "Filtering frames (blur, dedup)",
  dedup: "Checking for duplicates",
  ocr: "Running OCR",
  embed: "Generating embeddings",
  vlm: "VLM classification",
  finalize: "Persisting results",
};

export function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [adId, setAdId] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<LogLine[]>([]);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [finishedAt, setFinishedAt] = useState<number | null>(null);
  const [now, setNow] = useState(Date.now());
  const job = useJobEvents(jobId);
  const health = useApiHealth();
  const lastSig = useRef<string>("");
  const lastStage = useRef<string>("");

  const uploadMutation = useMutation({
    mutationFn: (selected: File) => api.uploadAd(selected),
    onSuccess: (result) => {
      setAdId(result.ad_id);
      setJobId(result.job_id ?? null);
      setStartedAt(Date.now());
      setFinishedAt(null);
      const lines: LogLine[] = [
        timestampedLog("ok", `accepted — ${result.ad_id}`),
      ];
      if (result.duplicate_of) {
        lines.push(timestampedLog("warn", `exact duplicate of ${result.duplicate_of} — skipping pipeline`));
      }
      setLogLines(lines);
    },
    onError: (err) => {
      setLogLines((prev) => [...prev, timestampedLog("warn", `upload failed: ${(err as Error).message}`)]);
    },
  });

  useEffect(() => {
    if (!startedAt || finishedAt) return;
    const handle = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(handle);
  }, [finishedAt, startedAt]);

  useEffect(() => {
    if (!job) return;
    const sig = `${job.state}|${job.progress ?? ""}|${job.message ?? ""}`;
    if (sig === lastSig.current) return;
    lastSig.current = sig;

    const level: LogLine["level"] = job.state === "failed" ? "warn" : job.state === "completed" ? "ok" : "info";
    const msg = job.message || job.state || "(no message)";
    const stageKey = job.message || "";

    // Emit a stage header when the stage changes
    if (stageKey && stageKey !== lastStage.current && STAGE_LABELS[stageKey]) {
      lastStage.current = stageKey;
      setLogLines((prev) => [
        ...prev,
        { ts: "", level: "info", message: `── ${STAGE_LABELS[stageKey]} ──` },
      ]);
    }

    setLogLines((prev) => [...prev, timestampedLog(level, `${job.state}: ${msg}`)]);
  }, [job]);

  const isDuplicateOrSkipped = Boolean(adId && jobId === null);
  const isDone = job?.state === "completed" || isDuplicateOrSkipped;
  const isTerminal = isDone || job?.state === "failed" || job?.state === "cancelled";

  useEffect(() => {
    if (isTerminal && startedAt && !finishedAt) setFinishedAt(Date.now());
  }, [finishedAt, isTerminal, startedAt]);

  const detailQuery = useQuery({
    queryKey: ["upload-detail", adId],
    queryFn: () => api.getAd(adId ?? ""),
    enabled: Boolean(isDone && adId),
  });

  const sizeText = useMemo(
    () => (file ? `${(file.size / (1024 * 1024)).toFixed(1)} MB` : ""),
    [file]
  );
  const elapsed = startedAt ? (finishedAt ?? now) - startedAt : 0;

  const reset = () => {
    setFile(null);
    setAdId(null);
    setJobId(null);
    setLogLines([]);
    setStartedAt(null);
    setFinishedAt(null);
    setNow(Date.now());
    lastStage.current = "";
    uploadMutation.reset();
  };

  const cancel = () => {
    if (jobId) void api.cancelJob(jobId);
  };

  const uploading = uploadMutation.isPending;
  const processing = adId && !isDone;

  return (
    <>
      <Topbar crumbs={["Workspace", "Upload"]} />
      <ApiOfflineBanner offline={health.isError} />

      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Upload ad</h1>
            <p className="page-sub">
              Drop a TV / promo / ad clip and the local pipeline extracts frames,
              transcript, OCR, entities, and classification — all on-device.
            </p>
          </div>
        </div>

        <div className="upload-layout">
          {/* ── left: input area ── */}
          <div className="upload-main">
            {!adId && !uploading ? (
              <>
                <Dropzone
                  onFile={(f) => {
                    setFile(f);
                    uploadMutation.mutate(f);
                  }}
                />

                {file && !uploading && (
                  <div className="upload-confirm">
                    <div className="upload-confirm-info">
                      <UploadIcon size={14} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="upload-confirm-name">{file.name}</div>
                        <div className="upload-confirm-meta">
                          {file.type || "video"} · {sizeText}
                        </div>
                      </div>
                      <button className="btn btn-icon" onClick={() => setFile(null)} title="Remove">
                        <CloseIcon size={12} />
                      </button>
                    </div>
                    <button
                      className="btn btn-primary upload-confirm-btn"
                      disabled={uploading}
                      onClick={() => uploadMutation.mutate(file)}
                    >
                      <UploadIcon size={12} />
                      <span>Classify this ad</span>
                    </button>
                  </div>
                )}

                {uploadMutation.isError && (
                  <div className="upload-error">
                    {(uploadMutation.error as Error).message}
                  </div>
                )}
              </>
            ) : null}

            {uploading && !adId ? (
              <div className="upload-queued">
                <span className="upload-queued-dot" />
                <span>Uploading and queuing for processing…</span>
              </div>
            ) : null}

            {processing && adId && (
              <PipelineProgress
                filename={file?.name ?? "clip"}
                adId={adId}
                jobId={jobId}
                job={job}
                elapsedMs={elapsed}
                logLines={logLines}
                onCancel={cancel}
              />
            )}
          </div>

          {/* ── right: result ── */}
          {isDone && detailQuery.data ? (
            <div className="upload-side">
              <ResultPanel
                detail={detailQuery.data}
                elapsedMs={elapsed}
                onReset={reset}
              />
            </div>
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
    message,
  };
}
