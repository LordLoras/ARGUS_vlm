export function Sparkline({
  values,
  color = "var(--accent-2)",
  width = 160,
  height = 18
}: {
  values: number[];
  color?: string;
  width?: number;
  height?: number;
}) {
  if (values.length < 2) {
    return <svg className="spark" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" />;
  }
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const dx = width / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * dx).toFixed(2)},${(height - ((v - min) / span) * height * 0.85 - 1).toFixed(2)}`)
    .join(" ");
  const fillPath = `M0,${height} L${points.split(" ").join(" L")} L${width},${height} Z`;
  const fillColor = color.startsWith("var(") ? "currentColor" : `${color}22`;
  return (
    <svg className="spark" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={{ color }}>
      <path d={fillPath} fill={fillColor} opacity={fillColor === "currentColor" ? 0.18 : 1} />
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.2} />
    </svg>
  );
}
