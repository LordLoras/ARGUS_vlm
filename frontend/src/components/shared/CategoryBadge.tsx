export function CategoryBadge({ category }: { category?: string | null }) {
  if (!category) return <span className="obs-empty">—</span>;
  return <span className="badge badge-mono">{category}</span>;
}
