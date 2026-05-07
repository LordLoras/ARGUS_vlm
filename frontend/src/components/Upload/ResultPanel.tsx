import { Link } from "react-router-dom";

import { filePathToDataUrl, formatTimestamp } from "../../lib/format";
import { sensitiveCategories } from "../../lib/taxonomy";
import type { AdDetail, FrameRecord, RelatedAds } from "../../lib/types";
import { ObservationTagPill } from "../shared/ObservationTagPill";
import { SensitivePill } from "../shared/SensitivePill";

export function ResultPanel({
  detail,
  frames,
  related,
  elapsedMs,
  onReset
}: {
  detail: AdDetail;
  frames: FrameRecord[];
  related?: RelatedAds;
  elapsedMs?: number;
  onReset: () => void;
}) {
  const cls = detail.classification;
  const category = cls?.primary_category ?? detail.ad.primary_category ?? "uncategorized";
  const sensitive = sensitiveCategories.has(category);
  const confidence = cls?.confidence ?? null;
  const risks = cls?.risk_labels ?? [];
  const ent = detail.marketing_entities?.entities;
  const evidence = (cls?.evidence ?? []).slice(0, 3);
  const videoSrc = filePathToDataUrl(detail.ad.source_path);

  return (
    <div className="upload-card" style={{ background: "transparent", border: 0, padding: 0 }}>
      <div className="result-hero">
        <div className="row" style={{ alignItems: "flex-start" }}>
          <div style={{ flex: 1 }}>
            <div className="lbl">Result</div>
            <div className="cat">{category}</div>
            <div className="row-meta">
              <span>confidence {confidence != null ? confidence.toFixed(2) : "—"}</span>
              <span>·</span>
              <span>{risks.length} observation tags</span>
              {elapsedMs ? (
                <>
                  <span>·</span>
                  <span>processed in {(elapsedMs / 1000).toFixed(1)}s</span>
                </>
              ) : null}
            </div>
          </div>
          {sensitive ? <SensitivePill sensitive /> : null}
        </div>
      </div>

      <Block title="Video preview">
        {videoSrc ? (
          <video src={videoSrc} controls playsInline style={{ width: "100%", borderRadius: 6, background: "#000" }} />
        ) : (
          <div className="obs-empty" style={{ padding: 24, textAlign: "center" }}>
            preview unavailable
          </div>
        )}
      </Block>

      <Block title="Brand & creative">
        <dl className="kv">
          <dt>Brand</dt>
          <dd>{ent?.brand?.name || detail.ad.brand_name || "—"}</dd>
          <dt>Tagline</dt>
          <dd>{ent?.brand?.tagline || "—"}</dd>
          <dt>Products</dt>
          <dd>{ent?.products?.join(", ") || detail.ad.products_text || "—"}</dd>
          <dt>Aspect ratio</dt>
          <dd className="mono">{ent?.creative_format?.aspect_ratio || "—"}</dd>
        </dl>
      </Block>

      <Block title="Offers & CTAs" count={(ent?.offers?.length ?? 0) + (ent?.ctas?.length ?? 0)}>
        {(ent?.offers ?? []).map((offer, idx) => (
          <div key={`offer-${idx}`} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
            <span className="badge badge-violet">{offer.type ?? "offer"}</span>
            <span style={{ flex: 1 }}>{offer.value || "—"}</span>
          </div>
        ))}
        {(ent?.ctas ?? []).map((cta, idx) => (
          <div key={`cta-${idx}`} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
            {cta.time_ms != null ? <span className="ts-link">{formatTimestamp(cta.time_ms)}</span> : null}
            <span style={{ flex: 1 }}>{cta.text || "—"}</span>
          </div>
        ))}
        {(ent?.offers ?? []).length === 0 && (ent?.ctas ?? []).length === 0 ? (
          <div className="obs-empty">No offers or CTAs detected.</div>
        ) : null}
      </Block>

      <Block title="Observation tags" count={risks.length}>
        {risks.length === 0 ? (
          <div className="obs-empty">No observation tags.</div>
        ) : (
          <div className="pill-row" style={{ gap: 6 }}>
            {risks.map((r) => (
              <ObservationTagPill key={r} label={r} />
            ))}
          </div>
        )}
      </Block>

      <Block title="Evidence highlights" count={evidence.length}>
        {evidence.length === 0 ? (
          <div className="obs-empty">No evidence stored.</div>
        ) : (
          evidence.map((item, idx) => {
            const frame = frames.find((f) => f.frame_index === item.frame_index);
            const src = frame ? filePathToDataUrl(frame.path) : "";
            return (
              <div key={`ev-${idx}`} className="evidence-row">
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
          })
        )}
      </Block>

      <Block title="Related ads" count={related?.semantically_similar?.length ?? 0}>
        {(related?.semantically_similar ?? []).length === 0 ? (
          <div className="obs-empty">No related ads indexed yet.</div>
        ) : (
          (related?.semantically_similar ?? []).slice(0, 3).map((item) => (
            <div
              key={item.ad_id}
              className="row"
              style={{ padding: "8px 0", borderBottom: "1px solid var(--border)", gap: 12 }}
            >
              <span className="mono" style={{ color: "var(--accent-2)", flex: 1 }}>
                {item.ad_id}
              </span>
              {item.verdict ? <span className="badge badge-violet">{item.verdict}</span> : null}
              {item.overall_score != null ? (
                <span className="mono" style={{ color: "var(--fg-mute)" }}>
                  {item.overall_score.toFixed(2)}
                </span>
              ) : null}
            </div>
          ))
        )}
      </Block>

      <div
        style={{
          display: "flex",
          gap: 10,
          marginTop: 12,
          justifyContent: "flex-end"
        }}
      >
        <button className="btn" onClick={onReset}>
          Upload another
        </button>
        <Link className="btn btn-primary" to={`/library?ad=${detail.ad.id}`}>
          Open full detail
        </Link>
      </div>
    </div>
  );
}

function Block({
  title,
  count,
  children
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="dcard">
      <div className="dcard-head">
        <span>{title}</span>
        {count != null ? <span className="count-pill">{count}</span> : null}
      </div>
      <div className="dcard-body">{children}</div>
    </div>
  );
}
