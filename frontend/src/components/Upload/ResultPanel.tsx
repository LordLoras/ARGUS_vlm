import { Link } from "react-router-dom";

import { filePathToDataUrl, formatTimestamp } from "../../lib/format";
import { formatPrice, priceContext } from "../../lib/marketing-display";
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
  const category = detail.ad.primary_category ?? cls?.primary_category ?? "uncategorized";
  const sensitive = sensitiveCategories.has(category);
  const confidence = cls?.confidence ?? null;
  const risks = cls?.risk_labels ?? [];
  const ent = detail.marketing_entities;
  const allEvidence = cls?.evidence ?? [];
  const evidence = allEvidence.slice(0, 3);
  const videoSrc = filePathToDataUrl(detail.ad.source_path);
  const products = detail.ad.products_text
    ? detail.ad.products_text.split(/,\s*/).filter(Boolean)
    : ent?.products ?? [];
  const disclaimers = ent?.disclaimers ?? [];
  const prices = ent?.prices ?? [];
  const offers = ent?.offers ?? [];
  const ctas = ent?.ctas ?? [];

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
          <div className="result-actions">
            <Link className="btn btn-primary" to={`/library?ad=${detail.ad.id}`}>
              Open full detail
            </Link>
            <button className="btn" onClick={onReset}>
              Upload another
            </button>
          </div>
        </div>
      </div>

      <Block title="Brand & product">
        <dl className="kv">
          <dt>Brand</dt>
          <dd>{detail.ad.brand_name || ent?.brand?.name || "—"}</dd>
          <dt>Tagline</dt>
          <dd>{ent?.brand?.tagline || "—"}</dd>
          <dt>Products</dt>
          <dd>{products.length ? products.join(", ") : "—"}</dd>
        </dl>
      </Block>

      <Block title="Prices, offers & CTAs" count={prices.length + offers.length + ctas.length}>
        {prices.map((price, idx) => {
          const evidence = price.evidence?.[0];
          const context = priceContext(price, allEvidence);
          return (
            <div key={`price-${idx}`} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
              {evidence?.time_ms != null ? (
                <span className="ts-link">{formatTimestamp(evidence.time_ms)}</span>
              ) : null}
              <span className="badge badge-violet">price</span>
              <span style={{ flex: 1 }}>
                <span>{formatPrice(price, context)}</span>
                {context ? <span className="price-context">{context}</span> : null}
              </span>
            </div>
          );
        })}
        {offers.map((offer, idx) => (
          <div key={`offer-${idx}`} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
            <span className="badge badge-violet">{offer.type ?? "offer"}</span>
            <span style={{ flex: 1 }}>{offer.text || offer.value || "—"}</span>
          </div>
        ))}
        {ctas.map((cta, idx) => (
          <div key={`cta-${idx}`} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
            {cta.time_ms != null || cta.evidence?.[0]?.time_ms != null ? (
              <span className="ts-link">{formatTimestamp(cta.time_ms ?? cta.evidence?.[0]?.time_ms)}</span>
            ) : null}
            <span style={{ flex: 1 }}>{cta.text || "—"}</span>
          </div>
        ))}
        {prices.length === 0 && offers.length === 0 && ctas.length === 0 ? (
          <div className="obs-empty">No prices, offers, or CTAs detected.</div>
        ) : null}
      </Block>

      <Block title="Video preview">
        {videoSrc ? (
          <video
            src={videoSrc}
            controls
            playsInline
            style={{ width: "100%", maxHeight: 460, objectFit: "contain", borderRadius: 6, background: "#000" }}
          />
        ) : (
          <div className="obs-empty" style={{ padding: 24, textAlign: "center" }}>
            preview unavailable
          </div>
        )}
      </Block>

      <Block title="Disclaimers" count={disclaimers.length}>
        {disclaimers.length === 0 ? (
          <div className="obs-empty">No disclaimers extracted.</div>
        ) : (
          disclaimers.map((disclaimer, idx) => {
            const timeMs = disclaimer.time_ms ?? disclaimer.evidence?.[0]?.time_ms;
            return (
              <div key={`disclaimer-${idx}`} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                {timeMs != null ? <span className="ts-link">{formatTimestamp(timeMs)}</span> : null}
                <span style={{ flex: 1 }}>{disclaimer.text || "—"}</span>
              </div>
            );
          })
        )}
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
