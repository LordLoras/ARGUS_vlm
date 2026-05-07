import type { RelatedAds } from "../../lib/types";

export function RelatedTab({ related }: { related?: RelatedAds }) {
  const items = related?.semantically_similar ?? [];
  if (items.length === 0 && !related?.exact_duplicate_of && !related?.near_duplicate_of) {
    return <div className="obs-empty">No related ads indexed yet.</div>;
  }
  return (
    <>
      {related?.exact_duplicate_of ? (
        <div className="dcard">
          <div className="dcard-head">
            <span>Exact duplicate</span>
          </div>
          <div className="dcard-body mono">{related.exact_duplicate_of}</div>
        </div>
      ) : null}
      {related?.near_duplicate_of ? (
        <div className="dcard">
          <div className="dcard-head">
            <span>Near duplicate</span>
          </div>
          <div className="dcard-body mono">{related.near_duplicate_of}</div>
        </div>
      ) : null}
      {items.length > 0 ? (
        <div className="dcard">
          <div className="dcard-head">
            <span>Semantically similar</span>
            <span className="count-pill">{items.length}</span>
          </div>
          <div className="dcard-body">
            {items.map((item) => (
              <div
                key={item.ad_id}
                style={{
                  display: "grid",
                  gridTemplateColumns: "120px 1fr auto",
                  gap: 12,
                  padding: "10px 0",
                  borderBottom: "1px solid var(--border)",
                  alignItems: "center"
                }}
              >
                <span className="mono" style={{ color: "var(--accent-2)" }}>
                  {item.ad_id}
                </span>
                <ScoreRow label="overall" value={item.overall_score} tone="overall" />
                {item.verdict ? <span className="badge badge-violet">{item.verdict}</span> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </>
  );
}

function ScoreRow({
  label,
  value,
  tone
}: {
  label: string;
  value?: number | null;
  tone?: "overall" | "visual" | "text";
}) {
  const pct = value ? Math.max(0, Math.min(1, value)) : 0;
  return (
    <div className="score-row">
      <span className="lbl">{label}</span>
      <div className={`score-bar ${tone ?? ""}`}>
        <span style={{ width: `${pct * 100}%` }} />
      </div>
      <span className="num">{value != null ? value.toFixed(2) : "—"}</span>
    </div>
  );
}
