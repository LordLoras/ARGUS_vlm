import { Badge } from "../ui/Badge";

export function ObservationTagPill({ label }: { label: string }) {
  return (
    <Badge title="descriptive observation tag - not a gating signal" className="font-mono">
      {label}
    </Badge>
  );
}
