export function ObservationTagPill({ label }: { label: string }) {
  return (
    <span className="obs-tag" title="Descriptive observation tag — not a gating signal">
      {label}
    </span>
  );
}

export function ObservationTagOverflow({ count }: { count: number }) {
  return <span className="obs-tag more">+{count}</span>;
}
