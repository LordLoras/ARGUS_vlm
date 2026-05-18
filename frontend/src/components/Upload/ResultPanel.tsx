import { Link } from "react-router-dom";

import { formatPrice, priceContext } from "../../lib/marketing-display";
import type { AdDetail } from "../../lib/types";
import { ObservationTagPill } from "../shared/ObservationTagPill";

export function ResultPanel({
  detail,
  elapsedMs,
  onReset
}: {
  detail: AdDetail;
  elapsedMs?: number;
  onReset: () => void;
}) {
  const cls = detail.classification;
  const category = detail.ad.primary_category ?? cls?.primary_category ?? "uncategorized";
  const confidence = cls?.confidence ?? null;
  const risks = cls?.risk_labels ?? [];
  const ent = detail.marketing_entities;
  const products = detail.ad.products_text
    ? detail.ad.products_text.split(/,\s*/).filter(Boolean)
    : ent?.products ?? [];
  const prices = ent?.prices ?? [];
  const offers = ent?.offers ?? [];
  const ctas = ent?.ctas ?? [];
  const disclaimers = ent?.disclaimers ?? [];
  const iab = cls?.iab_category;

  return (
    <div className="result-panel">
      <div className="result-hero">
        <div className="result-hero-cat">{category}</div>
        <div className="result-hero-meta">
          {confidence != null ? (
            <span className="result-hero-stat">
              confidence <strong>{confidence.toFixed(2)}</strong>
            </span>
          ) : null}
          <span className="result-hero-stat">
            {risks.length} tag{risks.length !== 1 ? "s" : ""}
          </span>
          {elapsedMs ? (
            <span className="result-hero-stat">
              {(elapsedMs / 1000).toFixed(1)}s
            </span>
          ) : null}
        </div>
      </div>

      <div className="result-section">
        <div className="result-section-title">Brand & advertiser</div>
        <dl className="result-kv">
          <dt>Brand</dt>
          <dd>{detail.ad.brand_name || ent?.brand?.name || "—"}</dd>
          <dt>Advertiser</dt>
          <dd>{detail.ad.advertiser_name || "—"}</dd>
          {ent?.brand?.tagline ? (
            <>
              <dt>Tagline</dt>
              <dd>{ent.brand.tagline}</dd>
            </>
          ) : null}
          <dt>Products</dt>
          <dd>{products.length ? products.join(", ") : "—"}</dd>
          <dt>IAB</dt>
          <dd>{iab?.full_path || detail.ad.iab_full_path || "—"}</dd>
        </dl>
      </div>

      {offers.length > 0 || prices.length > 0 || ctas.length > 0 ? (
        <div className="result-section">
          <div className="result-section-title">Offers & CTAs</div>
          <div className="result-chips">
            {offers.map((o, i) => (
              <span key={`o-${i}`} className="result-chip offer">
                {o.text || o.value || "—"}
              </span>
            ))}
            {prices.map((p, i) => (
              <span key={`p-${i}`} className="result-chip price">
                {formatPrice(p, priceContext(p, cls?.evidence ?? []))}
              </span>
            ))}
            {ctas.map((c, i) => (
              <span key={`c-${i}`} className="result-chip cta">
                {c.text || "—"}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {risks.length > 0 ? (
        <div className="result-section">
          <div className="result-section-title">Observation tags</div>
          <div className="result-tags">
            {risks.map((r) => (
              <ObservationTagPill key={r} label={r} />
            ))}
          </div>
        </div>
      ) : null}

      {disclaimers.length > 0 ? (
        <div className="result-section">
          <div className="result-section-title">Disclaimers</div>
          {disclaimers.map((d, i) => (
            <div key={`d-${i}`} className="result-disclaimer">
              {d.text || "—"}
            </div>
          ))}
        </div>
      ) : null}

      <div className="result-actions">
        <Link className="btn btn-primary" to={`/library?ad=${detail.ad.id}`}>
          Open in library
        </Link>
        <button className="btn" onClick={onReset}>
          Upload another
        </button>
      </div>
    </div>
  );
}
