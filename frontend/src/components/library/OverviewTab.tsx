import { formatPrice, priceContext } from "../../lib/marketing-display";
import type { AdDetail } from "../../lib/types";
import { ObservationTagPill } from "../shared/ObservationTagPill";
import { TimestampChip } from "../shared/TimestampChip";

export function OverviewTab({
  detail,
  onSeek
}: {
  detail: AdDetail;
  onSeek?: (timeMs: number) => void;
}) {
  const cls = detail.classification;
  const ent = detail.marketing_entities;
  const category = detail.ad.primary_category ?? cls?.primary_category ?? "uncategorized";
  const confidence = cls?.confidence ?? null;
  const risks = cls?.risk_labels ?? [];
  const prices = ent?.prices ?? [];
  const offers = ent?.offers ?? [];
  const ctas = ent?.ctas ?? [];
  const products = detail.ad.products_text
    ? detail.ad.products_text.split(/,\s*/).filter(Boolean)
    : ent?.products ?? [];
  const disclaimers = ent?.disclaimers ?? [];
  const subcategory = detail.ad.subcategory ?? ent?.subcategory ?? null;

  return (
    <>
      <Card title="Category">
        <div className="cat-row">
          <span className="cat-primary">{category}</span>
          <span className="cat-conf">{confidence != null ? `confidence ${confidence.toFixed(2)}` : "no confidence"}</span>
        </div>
        {subcategory ? (
          <div style={{ marginTop: 8 }}>
            <span className="badge badge-violet">{subcategory}</span>
          </div>
        ) : null}
      </Card>

      <Card title="Brand & product">
        <dl className="kv">
          <dt>Brand</dt>
          <dd>
            {detail.ad.brand_name || ent?.brand?.name || "—"}
            {ent?.brand?.logo_present ? (
              <span className="badge badge-violet" style={{ marginLeft: 6 }}>
                logo present
              </span>
            ) : null}
          </dd>
          <dt>Tagline</dt>
          <dd>{ent?.brand?.tagline || "—"}</dd>
          <dt>Products</dt>
          <dd>{products.length ? products.join(", ") : "—"}</dd>
        </dl>
      </Card>

      <Card title="Observation tags" count={risks.length}>
        {risks.length === 0 ? (
          <div className="obs-empty">No risk tags detected.</div>
        ) : (
          <div className="pill-row" style={{ gap: 6 }}>
            {risks.map((r) => (
              <ObservationTagPill key={r} label={r} />
            ))}
          </div>
        )}
      </Card>

      <Card title="Prices, offers & CTAs" count={prices.length + offers.length + ctas.length}>
        {prices.length === 0 && offers.length === 0 && ctas.length === 0 ? (
          <div className="obs-empty">No prices, offers, or CTAs extracted.</div>
        ) : null}
        {prices.length > 0 ? (
          <div style={{ marginBottom: 10 }}>
            <div className="section-title">Prices</div>
            {prices.map((price, idx) => {
              const evidence = price.evidence?.[0];
              const context = priceContext(price, cls?.evidence ?? []);
              return (
                <div key={`price-${idx}`} style={{ display: "flex", gap: 10, alignItems: "center", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                  <TimestampChip timeMs={evidence?.time_ms} onSeek={onSeek} />
                  <span className="badge badge-violet">price</span>
                  <span style={{ flex: 1 }}>
                    <span>{formatPrice(price, context)}</span>
                    {context ? <span className="price-context">{context}</span> : null}
                  </span>
                </div>
              );
            })}
          </div>
        ) : null}
        {offers.length > 0 ? (
          <div style={{ marginBottom: 10 }}>
            <div className="section-title">Offers</div>
            {offers.map((offer, idx) => (
              <div key={`offer-${idx}`} style={{ display: "flex", gap: 10, padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                <span className="badge badge-violet">{offer.type ?? "offer"}</span>
                <span style={{ flex: 1 }}>{offer.text || offer.value || "—"}</span>
                {offer.expiry_text ? <span className="mono" style={{ color: "var(--fg-mute)" }}>{offer.expiry_text}</span> : null}
              </div>
            ))}
          </div>
        ) : null}
        {ctas.length > 0 ? (
          <div>
            <div className="section-title">CTAs</div>
            {ctas.map((cta, idx) => (
              <div key={`cta-${idx}`} style={{ display: "flex", gap: 10, alignItems: "center", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                <TimestampChip timeMs={cta.time_ms ?? cta.evidence?.[0]?.time_ms} onSeek={onSeek} />
                <span style={{ flex: 1 }}>{cta.text || "—"}</span>
                {cta.destination_hint ? <span className="mono" style={{ color: "var(--fg-mute)" }}>{cta.destination_hint}</span> : null}
              </div>
            ))}
          </div>
        ) : null}
      </Card>

      <Card title="Disclaimers" count={disclaimers.length}>
        {disclaimers.length === 0 ? (
          <div className="obs-empty">No disclaimers extracted.</div>
        ) : (
          disclaimers.map((disclaimer, idx) => {
            const evidence = disclaimer.evidence?.[0];
            const timeMs = disclaimer.time_ms ?? evidence?.time_ms;
            return (
              <div key={`disclaimer-${idx}`} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                <TimestampChip timeMs={timeMs} onSeek={onSeek} />
                <span style={{ flex: 1 }}>{disclaimer.text || "—"}</span>
                {disclaimer.is_small_print ? <span className="badge badge-mono">small print</span> : null}
              </div>
            );
          })
        )}
      </Card>
    </>
  );
}

function Card({
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
