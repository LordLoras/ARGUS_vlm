import { Info } from "lucide-react";

import { Badge } from "../ui/Badge";

export function SensitivePill({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <Badge tone="amber" title="regulated content type; informational only">
      <Info className="mr-1 h-3 w-3" />
      Regulated
    </Badge>
  );
}
