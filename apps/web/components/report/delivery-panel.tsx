"use client";

import { useMemo } from "react";

import type { TurnOut } from "@/lib/api/types";

import { Sparkline } from "./sparkline";

function average(values: number[]): number {
  return values.length === 0 ? 0 : values.reduce((a, b) => a + b, 0) / values.length;
}

/** Task 3.3e: "Words per minute, filler rate, mean and longest answer, talk-time share, plotted
 * across the session... visually distinguished from model judgements — different treatment, not
 * the same score chip." No colour, no badge shape shared with components/score/ — plain numbers
 * and a monochrome trend line. */
export function DeliveryPanel({ turns, sessionDurationMs }: { turns: TurnOut[]; sessionDurationMs: number | null }) {
  const userTurns = useMemo(() => turns.filter((t) => t.speaker === "user" && t.metrics), [turns]);

  if (userTurns.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-4 text-center text-xs text-[var(--text-tertiary)]">
        No answers with measurable delivery yet.
      </div>
    );
  }

  const wpmSeries = userTurns.map((t) => t.metrics!.wpm);
  const fillerRates = userTurns.map((t) => t.metrics!.filler_rate);
  const wordCounts = userTurns.map((t) => t.metrics!.word_count);
  const totalUserMs = userTurns.reduce((sum, t) => sum + (t.end_ms - t.start_ms), 0);
  const talkTimeShare = sessionDurationMs ? totalUserMs / sessionDurationMs : null;

  const stats = [
    { label: "Words per minute", value: `${Math.round(average(wpmSeries))}`, series: wpmSeries },
    {
      label: "Filler rate",
      value: `${(average(fillerRates) * 100).toFixed(1)}%`,
      series: fillerRates.map((r) => r * 100),
    },
    { label: "Mean answer length", value: `${Math.round(average(wordCounts))} words`, series: wordCounts },
    {
      label: "Longest answer",
      value: `${Math.max(...wordCounts)} words`,
      series: null,
    },
    {
      label: "Talk-time share",
      value: talkTimeShare !== null ? `${Math.round(talkTimeShare * 100)}%` : "—",
      series: null,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {stats.map((s) => (
        <div key={s.label} className="rounded-lg border bg-[var(--bg-card)] p-3">
          <p className="text-xs text-[var(--text-tertiary)]">{s.label}</p>
          <div className="mt-1 flex items-end justify-between gap-2">
            <span className="font-mono text-md">{s.value}</span>
            {s.series && s.series.length > 1 && <Sparkline values={s.series} />}
          </div>
        </div>
      ))}
    </div>
  );
}
