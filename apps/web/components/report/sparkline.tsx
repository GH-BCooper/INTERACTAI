/** A single-series magnitude sparkline — deliberately monochrome (docs/phase-3-BUILD.md TASK
 * 3.3e: delivery metrics must read as "arithmetic," never compete visually with the reserved
 * score colours used elsewhere on this page for rubric judgements). One series needs no legend
 * (the panel's own label names it) and no axis — this is a shape, not a plot to be read
 * precisely. Text stays in text tokens; only the line itself carries the (neutral) colour. */
export function Sparkline({ values, height = 32 }: { values: number[]; height?: number }) {
  if (values.length < 2) return null;

  const width = 160;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = width / (values.length - 1);

  const points = values.map((v, i) => {
    const x = i * stepX;
    const y = height - ((v - min) / span) * (height - 6) - 3;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Trend across ${values.length} turns, from ${min.toFixed(0)} to ${max.toFixed(0)}`}
      className="overflow-visible"
    >
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke="var(--text-secondary)"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={points.at(-1)!.split(",")[0]}
        cy={points.at(-1)!.split(",")[1]}
        r={3}
        fill="var(--text-secondary)"
      />
    </svg>
  );
}
