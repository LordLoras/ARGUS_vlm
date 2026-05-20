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
import type { JobRecord } from "../lib/types";

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

const UPLOAD_SESSION_KEY = "argus:last-upload-job";

type UploadSession = {
  adId: string;
  jobId: string | null;
  fileName: string | null;
  startedAt: number;
  finishedAt?: number | null;
};

export function Upload() {
  const restoredSession = useMemo(readUploadSession, []);
  const [file, setFile] = useState<File | null>(null);
  const [restoredFileName, setRestoredFileName] = useState<string | null>(
    restoredSession?.fileName ?? null
  );
  const [adId, setAdId] = useState<string | null>(restoredSession?.adId ?? null);
  const [jobId, setJobId] = useState<string | null>(restoredSession?.jobId ?? null);
  const [logLines, setLogLines] = useState<LogLine[]>(() =>
    restoredSession
      ? [timestampedLog("info", `restored upload — ${restoredSession.adId}`)]
      : []
  );
  const [startedAt, setStartedAt] = useState<number | null>(restoredSession?.startedAt ?? null);
  const [finishedAt, setFinishedAt] = useState<number | null>(
    restoredSession?.finishedAt ?? null
  );
  const [now, setNow] = useState(Date.now());
  const job = useJobEvents(jobId);
  const health = useApiHealth();
  const lastSig = useRef<string>("");
  const lastStage = useRef<string>("");

  const uploadMutation = useMutation({
    mutationFn: (selected: File) => api.uploadAd(selected),
    onSuccess: (result, selected) => {
      const started = Date.now();
      setAdId(result.ad_id);
      setJobId(result.job_id ?? null);
      setStartedAt(started);
      setFinishedAt(null);
      setRestoredFileName(selected.name);
      writeUploadSession({
        adId: result.ad_id,
        jobId: result.job_id ?? null,
        fileName: selected.name,
        startedAt: started,
        finishedAt: null
      });
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

  const recentJobsQuery = useQuery({
    queryKey: ["upload-recent-jobs"],
    queryFn: () => api.listJobs({ limit: 5 }),
    enabled: !adId && !uploadMutation.isPending,
    refetchInterval: 3000
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
    if (!isTerminal || !startedAt || finishedAt) return;
    const finished = Date.now();
    setFinishedAt(finished);
    if (adId) {
      writeUploadSession({
        adId,
        jobId,
        fileName: file?.name ?? restoredFileName,
        startedAt,
        finishedAt: finished
      });
    }
  }, [adId, file, finishedAt, isTerminal, jobId, restoredFileName, startedAt]);

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
    setRestoredFileName(null);
    clearUploadSession();
    uploadMutation.reset();
  };

  const restoreJob = (candidate: JobRecord) => {
    if (!candidate.ad_id) return;
    const started = timestampFrom(candidate.started_at || candidate.ingested_at) ?? Date.now();
    const finished = timestampFrom(candidate.finished_at);
    const fileName = filenameFromPath(candidate.source_path) ?? candidate.ad_id;
    setFile(null);
    setAdId(candidate.ad_id);
    setJobId(candidate.id);
    setStartedAt(started);
    setFinishedAt(finished);
    setRestoredFileName(fileName);
    setLogLines([timestampedLog("info", `restored job — ${candidate.id}`)]);
    lastSig.current = "";
    lastStage.current = "";
    writeUploadSession({
      adId: candidate.ad_id,
      jobId: candidate.id,
      fileName,
      startedAt: started,
      finishedAt: finished
    });
  };

  const cancel = () => {
    if (jobId) void api.cancelJob(jobId);
  };

  const uploading = uploadMutation.isPending;
  const processing = adId && !isDone;
  const displayFileName = file?.name ?? restoredFileName ?? "clip";

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

                {recentJobsQuery.data?.items.length ? (
                  <div className="upload-confirm" style={{ gap: 8 }}>
                    <div className="section-title" style={{ marginBottom: 0 }}>
                      Recent jobs
                    </div>
                    {recentJobsQuery.data.items.map((candidate) => (
                      <button
                        key={candidate.id}
                        className="btn"
                        style={{ justifyContent: "space-between", height: "auto", padding: 8 }}
                        disabled={!candidate.ad_id}
                        onClick={() => restoreJob(candidate)}
                      >
                        <span className="mono">{candidate.ad_id || candidate.id}</span>
                        <span className={`badge ${stateBadge(candidate.state)}`}>
                          {candidate.state}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : null}
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
                filename={displayFileName}
                adId={adId}
                jobId={jobId}
                job={job}
                elapsedMs={elapsed}
                logLines={logLines}
                onCancel={cancel}
              />
            )}

            {isDone && detailQuery.data ? (
              <ResultPanel
                detail={detailQuery.data}
                elapsedMs={elapsed}
                onReset={reset}
              />
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}

function readUploadSession(): UploadSession | null {
  try {
    const raw = window.localStorage.getItem(UPLOAD_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<UploadSession>;
    if (!parsed.adId || typeof parsed.adId !== "string") return null;
    return {
      adId: parsed.adId,
      jobId: typeof parsed.jobId === "string" ? parsed.jobId : null,
      fileName: typeof parsed.fileName === "string" ? parsed.fileName : null,
      startedAt: typeof parsed.startedAt === "number" ? parsed.startedAt : Date.now(),
      finishedAt: typeof parsed.finishedAt === "number" ? parsed.finishedAt : null
    };
  } catch {
    return null;
  }
}

function writeUploadSession(session: UploadSession) {
  window.localStorage.setItem(UPLOAD_SESSION_KEY, JSON.stringify(session));
}

function clearUploadSession() {
  window.localStorage.removeItem(UPLOAD_SESSION_KEY);
}

function timestampFrom(value?: string | null) {
  if (!value) return null;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

function filenameFromPath(value?: string | null) {
  if (!value) return null;
  return value.split(/[\\/]/).filter(Boolean).at(-1) ?? null;
}

function stateBadge(state: string) {
  if (state === "running") return "badge-sky";
  if (state === "queued") return "badge-violet";
  if (state === "completed") return "badge-emerald";
  if (state === "failed") return "badge-rose";
  return "badge-mono";
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
