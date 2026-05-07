import { useEffect, useRef, useState } from "react";

import { CloseIcon, CopyIcon, EditIcon, PlayIcon, PlusIcon, TrashIcon } from "../lib/icons";
import { filePathToDataUrl } from "../lib/format";
import type { AdDetail, FrameRecord, RelatedAds } from "../lib/types";
import { EditTab, type EditPatch } from "./library/EditTab";
import { EvidenceTab } from "./library/EvidenceTab";
import { OverviewTab } from "./library/OverviewTab";
import { RelatedTab } from "./library/RelatedTab";

const TABS = ["Overview", "Evidence", "Related", "Edit"] as const;
type Tab = (typeof TABS)[number];

export function AdDetailDrawer({
  detail,
  frames,
  related,
  onClose,
  onSave,
  onDelete,
  saving
}: {
  detail: AdDetail;
  frames: FrameRecord[];
  related?: RelatedAds;
  onClose: () => void;
  onSave: (patch: EditPatch) => void;
  onDelete: () => void;
  saving?: boolean;
}) {
  const [tab, setTab] = useState<Tab>("Overview");
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const evidenceCount = detail.classification?.evidence?.length ?? 0;
  const relatedCount = related?.semantically_similar?.length ?? 0;
  const videoSrc = filePathToDataUrl(detail.ad.source_path);
  const videoAspect =
    detail.ad.width && detail.ad.height ? `${detail.ad.width} / ${detail.ad.height}` : "16 / 9";

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const seekVideo = (timeMs: number) => {
    const video = videoRef.current;
    if (!video) return;
    const seekSeconds = Math.max(0, timeMs / 1000);
    video.currentTime = seekSeconds;
    video.dataset.seekMs = String(timeMs);
    void video.play().catch(() => {
      // Browser autoplay rules can still block playback; the seek itself is the important action.
    });
  };

  return (
    <>
      <div className="drawer-overlay open" onClick={onClose} />
      <aside className="drawer open" onClick={(e) => e.stopPropagation()}>
        <header className="drawer-head">
          <span className="ad-id" title={detail.ad.id}>
            {detail.ad.id}
            <button
              className="btn-ghost"
              style={{ background: "transparent", border: 0, color: "var(--fg-quiet)", cursor: "pointer" }}
              onClick={() => navigator.clipboard.writeText(detail.ad.id)}
              title="Copy id"
            >
              <CopyIcon size={11} />
            </button>
          </span>
          <span style={{ color: "var(--fg-mute)", fontSize: 12 }}>
            {detail.ad.brand_name || "Unknown brand"}
          </span>
          <span style={{ color: "var(--fg-quiet)" }}>·</span>
          <span className="mono" style={{ color: "var(--accent-2)", fontSize: 12 }}>
            {detail.ad.primary_category ?? detail.classification?.primary_category ?? "uncategorized"}
          </span>
          <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
            <button className="btn btn-sm" onClick={() => setTab("Edit")}>
              <EditIcon size={11} />
              <span>Edit</span>
            </button>
            <button className="btn btn-sm" disabled title="Phase 9: campaign assignment">
              <PlusIcon size={11} />
              <span>Add to campaign</span>
            </button>
            <button className="btn btn-sm btn-icon btn-danger" onClick={onDelete} title="Delete">
              <TrashIcon size={11} />
            </button>
            <button className="btn btn-sm btn-icon btn-ghost" onClick={onClose} title="Close (Esc)">
              <CloseIcon size={12} />
            </button>
          </div>
        </header>

        <div className="drawer-body">
          <div className="video-stage" style={{ aspectRatio: videoAspect }}>
            {videoSrc ? (
              <video
                ref={videoRef}
                src={videoSrc}
                controls
                playsInline
                style={{ position: "relative", zIndex: 1, width: "100%", height: "100%", objectFit: "contain", background: "#000" }}
              />
            ) : (
              <>
                <div className="video-text">
                  <div className="play-circle">
                    <PlayIcon size={20} />
                  </div>
                  <div>preview unavailable</div>
                </div>
                <div className="video-controls">
                  <span>0:00</span>
                  <div className="video-progress">
                    <span />
                    <span className="marker" style={{ left: "12%" }} />
                    <span className="marker" style={{ left: "38%" }} />
                    <span className="marker" style={{ left: "61%" }} />
                  </div>
                  <span>{detail.ad.duration_ms ? `${(detail.ad.duration_ms / 1000).toFixed(1)}s` : "—"}</span>
                </div>
              </>
            )}
          </div>

          <div className="tabs">
            {TABS.map((label) => (
              <span
                key={label}
                className={`tab ${tab === label ? "active" : ""}`}
                onClick={() => setTab(label)}
              >
                {label}
                {label === "Evidence" ? <span className="count">{evidenceCount}</span> : null}
                {label === "Related" ? <span className="count">{relatedCount}</span> : null}
              </span>
            ))}
          </div>

          <div className="tab-pane">
            {tab === "Overview" ? <OverviewTab detail={detail} onSeek={seekVideo} /> : null}
            {tab === "Evidence" ? (
              <EvidenceTab classification={detail.classification} frames={frames} onSeek={seekVideo} />
            ) : null}
            {tab === "Related" ? <RelatedTab related={related} /> : null}
            {tab === "Edit" ? <EditTab detail={detail} onSave={onSave} saving={saving} /> : null}
          </div>
        </div>
      </aside>
    </>
  );
}
