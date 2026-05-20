import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiOfflineBanner } from "../components/shared/ApiOfflineBanner";
import { EmptyState } from "../components/shared/EmptyState";
import { Topbar } from "../components/Topbar";
import { useApiHealth } from "../hooks/useApiHealth";
import { api } from "../lib/api-client";
import { CloseIcon, TrashIcon, UploadIcon } from "../lib/icons";
import type { JobRecord } from "../lib/types";

const STATES = ["", "running", "queued", "failed", "cancelled", "completed"];
const ACTIVE_STATES = new Set(["running", "queued"]);

export function Jobs() {
  const queryClient = useQueryClient();
  const health = useApiHealth();
  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.listJobs({ limit: 100 }),
    refetchInterval: 2000
  });

  const cancelMutation = useMutation({
    mutationFn: (jobId: string) => api.cancelJob(jobId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["jobs"] })
  });
  const deleteMutation = useMutation({
    mutationFn: (jobId: string) => api.deleteJob(jobId, true),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["ads"] });
    }
  });

  const jobs = jobsQuery.data?.items ?? [];

  return (
    <>
      <Topbar crumbs={["System", "Jobs"]} />
      <ApiOfflineBanner offline={health.isError} />
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Jobs</h1>
            <p className="page-sub">
              Watch queued and running ingest jobs, cancel stuck work, and remove partial ad artifacts.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Link className="btn btn-primary" to="/upload">
              <UploadIcon size={12} />
              <span>Upload</span>
            </Link>
            <button className="btn" onClick={() => void jobsQuery.refetch()}>
              Refresh
            </button>
          </div>
        </div>

        <div style={{ padding: "0 18px 18px", display: "grid", gap: 12 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {STATES.map((state) => {
              const count = state ? jobs.filter((job) => job.state === state).length : jobs.length;
              return (
                <span key={state || "all"} className="badge badge-mono">
                  {state || "all"} {count}
                </span>
              );
            })}
          </div>

          <div className="table-wrap" style={{ border: "1px solid var(--border)", borderRadius: 8 }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Job</th>
                  <th>State</th>
                  <th>Progress</th>
                  <th>Message</th>
                  <th>Ad</th>
                  <th>Started</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    cancelling={cancelMutation.isPending}
                    deleting={deleteMutation.isPending}
                    onCancel={() => cancelMutation.mutate(job.id)}
                    onDelete={() => {
                      const action = ACTIVE_STATES.has(job.state)
                        ? "Cancel this job and delete its ad rows and generated artifacts?"
                        : "Delete this job, ad rows, and generated artifacts?";
                      if (window.confirm(action)) deleteMutation.mutate(job.id);
                    }}
                  />
                ))}
              </tbody>
            </table>
            {jobs.length === 0 ? (
              <div style={{ padding: 28 }}>
                <EmptyState title="No jobs" hint="Upload an ad to create a pipeline job." />
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}

function JobRow({
  job,
  cancelling,
  deleting,
  onCancel,
  onDelete
}: {
  job: JobRecord;
  cancelling: boolean;
  deleting: boolean;
  onCancel: () => void;
  onDelete: () => void;
}) {
  const progress = Math.round((job.progress ?? 0) * 100);
  const canCancel = ACTIVE_STATES.has(job.state);
  return (
    <tr>
      <td className="mono">
        <div style={{ display: "grid", gap: 2 }}>
          <span>{job.id}</span>
          {job.error ? <span style={{ color: "var(--rose)" }}>{job.error}</span> : null}
        </div>
      </td>
      <td>
        <span className={`badge ${stateBadge(job.state)}`}>{job.state}</span>
      </td>
      <td className="mono">{progress}%</td>
      <td style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis" }}>
        {job.message || "-"}
      </td>
      <td className="mono" style={{ maxWidth: 270, overflow: "hidden", textOverflow: "ellipsis" }}>
        {job.ad_id ? (
          <Link to={`/library?ad=${job.ad_id}`} style={{ color: "var(--accent-2)" }}>
            {job.ad_id}
          </Link>
        ) : (
          "-"
        )}
        {job.ad_status ? <span style={{ color: "var(--fg-mute)" }}> / {job.ad_status}</span> : null}
      </td>
      <td className="mono">{formatDate(job.started_at || job.ingested_at)}</td>
      <td>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 6 }}>
          <button
            className="btn btn-sm"
            disabled={!canCancel || cancelling}
            onClick={onCancel}
            title="Cancel queued or running job"
          >
            <CloseIcon size={11} />
            <span>Cancel</span>
          </button>
          <button
            className="btn btn-sm btn-danger"
            disabled={deleting}
            onClick={onDelete}
            title="Delete job, ad rows, and generated files"
          >
            <TrashIcon size={11} />
            <span>Delete</span>
          </button>
        </div>
      </td>
    </tr>
  );
}

function stateBadge(state: string) {
  if (state === "running") return "badge-sky";
  if (state === "queued") return "badge-violet";
  if (state === "completed") return "badge-emerald";
  if (state === "failed") return "badge-rose";
  return "badge-mono";
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
