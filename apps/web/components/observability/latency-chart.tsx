import type { LatencyHeaderOut } from "@/lib/api/types";

const W = 640;
const H = 200;
const PAD = { l: 48, r: 12, t: 12, b: 24 };

const SERIES = [
  { key: "p50", label: "p50", className: "stroke-[var(--text-tertiary)]" },
  { key: "p90", label: "p90", className: "stroke-[var(--text-secondary)]" },
  { key: "p95", label: "p95", className: "stroke-[var(--accent)]" },
] as const;

/** TASK 6.1a: "The target line (1400 ms p95) is drawn on the chart. A chart without the line is
 * data; a chart with it is an argument." Every point is a day's e2e percentile, computed by
 * Postgres from `stage = 'e2e'` rows — never a sum of stage percentiles. */
export function LatencyChart({ data }: { data: LatencyHeaderOut }) {
  const points = data.series;
  const values = points.flatMap((p) => [p.p50, p.p90, p.p95]).filter((v): v is number => v !== null);
  const yMax = Math.max(data.target_p95_ms * 1.2, ...values) * 1.05;
  const x = (i: number) =>
    PAD.l + (points.length <= 1 ? (W - PAD.l - PAD.r) / 2 : (i / (points.length - 1)) * (W - PAD.l - PAD.r));
  const y = (v: number) => PAD.t + (1 - v / yMax) * (H - PAD.t - PAD.b);
  const targetY = y(data.target_p95_ms);
  const ticks = [0, yMax / 2, yMax].map((v) => Math.round(v / 100) * 100);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="End-to-end latency percentiles per day with the 1400 ms p95 target line">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="stroke-[var(--border-subtle)]" />
          <text x={PAD.l - 6} y={y(t) + 4} textAnchor="end" className="fill-[var(--text-tertiary)] text-[10px]">
            {t}
          </text>
        </g>
      ))}
      <line
        x1={PAD.l}
        x2={W - PAD.r}
        y1={targetY}
        y2={targetY}
        strokeDasharray="6 4"
        strokeWidth={2}
        className="stroke-[var(--danger)]"
      />
      <text x={W - PAD.r} y={targetY - 6} textAnchor="end" className="fill-[var(--danger)] text-[11px] font-medium">
        target p95 {data.target_p95_ms} ms
      </text>
      {SERIES.map((s) => {
        const pts = points
          .map((p, i) => (p[s.key] === null ? null : `${x(i)},${y(p[s.key] as number)}`))
          .filter((v): v is string => v !== null);
        return (
          <g key={s.key}>
            <polyline points={pts.join(" ")} fill="none" strokeWidth={s.key === "p95" ? 2.5 : 1.5} className={s.className} />
            {pts.map((pt) => {
              const [cx, cy] = pt.split(",");
              return <circle key={pt} cx={cx} cy={cy} r={2.5} className={`fill-[var(--bg-card)] ${s.className}`} />;
            })}
          </g>
        );
      })}
      {points.map((p, i) => (
        <text key={p.bucket} x={x(i)} y={H - 6} textAnchor="middle" className="fill-[var(--text-tertiary)] text-[10px]">
          {p.bucket.slice(5, 10)}
        </text>
      ))}
    </svg>
  );
}
