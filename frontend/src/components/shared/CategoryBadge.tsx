import { Badge } from "../ui/Badge";

export function CategoryBadge({ category }: { category?: string | null }) {
  return <Badge tone="accent">{category || "uncategorized"}</Badge>;
}
