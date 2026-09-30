"use client";

import { clsx } from "clsx";
import { useState } from "react";

import { LocalDate } from "@/components/ui/local-date";
import type { WeeklyVolumePointOut } from "@/lib/api/types";

const CHART_HEIGHT = 120; // px, plot area

function niceMax(value: number): number {
  if (value <= 5) return 5;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = magnitude / 2;
  return Math.ceil(value / step) * step;
}

/** docs/ui-audit-2026-09.md §10: minutes practised per week as a small, readable bar chart — a
 * y-axis with gridlines, the value on the hovered/focused bar, and a real tooltip instead of a
 * `title`. One series, neutral colour (it is measured volume, never a rubric value). Each bar is
 * focusable so the numbers are reachable without a mouse. */
export function WeeklyVolumeChart({ weeks }: { weeks: WeeklyVolumePointOut[] }) {
  const [active, setActive] = useState<string | null>(null);
  const max = niceMax(Math.max(0, ...weeks.map((w) => w.minutes)));
  const ticks = [max, max / 2, 0];

  return (
    <div className="flex gap-2">
      <div className="relative w-8 shrink-0 text-right font-mono text-xs text-[var(--text-tertiary)]" style={{ height: CHART_HEIGHT }}>
        {ticks.map((t) => (
          <span key={t} className="absolute right-0 -translate-y-1/2" style={{ top: `${(1 - t / max) * 100}%` }}>
            {Number.isInteger(t) ? t : t.toFixed(1)}
          </span>
        ))}
      </div>
      <div className="min-w-0 flex-1">
        <div className="relative" style={{ height: CHART_HEIGHT }}>
          {ticks.map((t) => (
            <div
              key={t}
              aria-hidden
              className={clsx("absolute inset-x-0 border-t", t === 0 ? "border-[var(--border)]" : "border-dashed border-[var(--border-subtle)]")}
              style={{ top: `${(1 - t / max) * 100}%` }}
            />
          ))}
          <ul className="absolute inset-0 flex items-end gap-1.5" aria-label="Minutes practised per week">
            {weeks.map((w) => {
              const isActive = active === w.week_start;
              return (
                <li key={w.week_start} className="relative flex h-full flex-1 items-end justify-center">
                  <button
                    type="button"
                    onMouseEnter={() => setActive(w.week_start)}
                    onMouseLeave={() => setActive(null)}
                    onFocus={() => setActive(w.week_start)}
                    onBlur={() => setActive(null)}
                    aria-label={`Week of ${new Date(w.week_start).toDateString()}: ${w.minutes} minutes, ${w.sessions} sessions`}
                    className={clsx(
                      "w-full max-w-10 rounded-t transition-colors duration-150",
                      isActive ? "bg-[var(--accent)]" : "bg-[var(--text-tertiary)]/60",
                    )}
                    style={{ height: `${Math.max(2, (w.minutes / max) * 100)}%` }}
                  />
                  {isActive && (
                    <div
                      role="tooltip"
                      className="pointer-events-none absolute bottom-full z-10 mb-1 whitespace-nowrap rounded-md border bg-[var(--bg-raised)] px-2 py-1 text-xs animate-fade-in"
                    >
                      <span className="font-mono">{w.minutes} min</span>
                      <span className="text-[var(--text-tertiary)]"> · {w.sessions} session{w.sessions === 1 ? "" : "s"}</span>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
        <div className="mt-1 flex gap-1.5" aria-hidden>
          {weeks.map((w, i) => (
            <span key={w.week_start} className="flex-1 truncate text-center text-xs text-[var(--text-tertiary)]">
              {/* Every other label when crowded, so they never overlap. */}
              {weeks.length <= 8 || i % 2 === 0 ? <LocalDate value={w.week_start} options={{ month: "short", day: "numeric" }} /> : ""}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
