import { formatTimestamp } from "../../lib/format";
import { sensitiveCategories } from "../../lib/taxonomy";
import type { AdDetail } from "../../lib/types";
import { ObservationTagPill } from "../shared/ObservationTagPill";
import { SensitivePill } from "../shared/SensitivePill";

export function OverviewTab({ detail }: { detail: AdDetail }) {
  const cls = detail.classification;
  const ent = detail.marketing_entities?.entities;
  const category = cls?.primary_category ?? detail.ad.primary_category ?? "uncategorized";
  const sensitive = sensitiveCategories.has(category);
  const confidence = cls?.confidence ?? null;
  const risks = cls?.risk_labels ?? [];
  const offers = ent?.offers ?? [];
  const ctas = ent?.ctas ?? [];
  const products = ent?.products ?? (detail.ad.products_text ? detail.ad.products_text.split(/,\s*/) : []);
  const social = ent?.social_proof;
  const disclaimers = ent?.disclaimers ?? [];

  return (
    <>
      <Card title="Category">
        <div className="cat-row">
          <span className="cat-primary">{category}</span>
          <span className="cat-conf">{confidence != null ? `confidence ${confidence.toFixed(2)}` : "no confidence"}</span>
        </div>
        {sensitive ? (
          <div style={{ marginTop: 10 }}>
            <SensitivePill sensitive />
          </div>
        ) : null}
      </Card>

      <Card title="Brand & creative">
        <dl className="kv">
          <dt>Brand</dt>
          <dd>
            {ent?.brand?.name || detail.ad.brand_name || "—"}
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
          <dt>Aspect ratio</dt>
          <dd className="mono">{ent?.creative_format?.aspect_ratio || "—"}</dd>
          <dt>Voiceover</dt>
          <dd>{formatBool(ent?.creative_format?.has_voiceover)}</dd>
          <dt>On-screen text</dt>
          <dd>{formatBool(ent?.creative_format?.has_on_screen_text)}</dd>
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

      <Card title="Offers & CTAs" count={offers.length + ctas.length}>
        {offers.length === 0 && ctas.length === 0 ? (
          <div className="obs-empty">No offers or CTAs extracted.</div>
        ) : null}
        {offers.length > 0 ? (
          <div style={{ marginBottom: 10 }}>
            <div className="section-title">Offers</div>
            {offers.map((offer, idx) => (
              <div key={`offer-${idx}`} style={{ display: "flex", gap: 10, padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                <span className="badge badge-violet">{offer.type ?? "offer"}</span>
                <span style={{ flex: 1 }}>{offer.value || "—"}</span>
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
                {cta.time_ms != null ? <span className="ts-link">{formatTimestamp(cta.time_ms)}</span> : null}
                <span style={{ flex: 1 }}>{cta.text || "—"}</span>
                {cta.destination_hint ? <span className="mono" style={{ color: "var(--fg-mute)" }}>{cta.destination_hint}</span> : null}
              </div>
            ))}
          </div>
        ) : null}
      </Card>

      <Card title="Social proof & disclaimers">
        <dl className="kv">
          <dt>Rating</dt>
          <dd>{social?.rating ?? "—"}</dd>
          <dt>Rating count</dt>
          <dd>{social?.rating_count ?? "—"}</dd>
          <dt>Testimonials</dt>
          <dd>{social?.testimonials?.length ? social.testimonials.join(" · ") : "—"}</dd>
          <dt>Badges</dt>
          <dd>{social?.badges?.length ? social.badges.join(", ") : "—"}</dd>
          <dt>Disclaimers</dt>
          <dd>{disclaimers.length ? `${disclaimers.length} captured` : "—"}</dd>
        </dl>
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

function formatBool(value: boolean | null | undefined) {
  if (value == null) return "—";
  return value ? "Yes" : "No";
}
