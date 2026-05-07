export function SensitivePill({ sensitive }: { sensitive: boolean }) {
  if (!sensitive) return <span className="obs-empty">—</span>;
  return (
    <span
      className="sensitive-pill"
      title="Regulated content type — informational only, not a gating signal"
    >
      Regulated
      <span className="info-i">i</span>
    </span>
  );
}
