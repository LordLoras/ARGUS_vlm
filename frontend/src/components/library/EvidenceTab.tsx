import { filePathToDataUrl, formatTimestamp } from "../../lib/format";
import type { ClassificationRecord, FrameRecord } from "../../lib/types";

export function EvidenceTab({
  classification,
  frames
}: {
  classification?: ClassificationRecord | null;
  frames: FrameRecord[];
}) {
  const items = classification?.evidence ?? [];
  if (items.length === 0) {
    return <div className="obs-empty">No evidence stored for this ad.</div>;
  }
  return (
    <div className="dcard">
      <div className="dcard-head">
        <span>Timestamped evidence</span>
        <span className="count-pill">{items.length}</span>
      </div>
      <div className="dcard-body">
        {items.map((item, index) => {
          const frame = frames.find((f) => f.frame_index === item.frame_index);
          const src = frame ? filePathToDataUrl(frame.path) : "";
          return (
            <div className="evidence-row" key={`${item.frame_index}-${index}`}>
              <div className="evidence-thumb">
                {src ? <img className="thumb-img" src={src} alt="" loading="lazy" /> : null}
              </div>
              <span className="ts-link">{formatTimestamp(item.time_ms)}</span>
              <span className="badge badge-mono">{item.source ?? "—"}</span>
              <div className="evidence-text">
                <span>{item.text || "—"}</span>
                {item.reason ? <span className="reason">{item.reason}</span> : null}
              </div>
              <span className="mono" style={{ color: "var(--fg-quiet)", textAlign: "right" }}>
                {typeof item.confidence === "number" ? item.confidence.toFixed(2) : "—"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
