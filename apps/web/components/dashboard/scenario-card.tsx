"use client";

import { ScoreBadge } from "@/components/score/score-badge";
import type { ScenarioOut } from "@/lib/api/types";

export function ScenarioCard({
  scenario,
  onStart,
  bestScore = null,
}: {
  scenario: ScenarioOut;
  onStart: () => void;
  bestScore?: number | null;
}) {
  return (
    <button
      type="button"
      onClick={onStart}
      className="flex flex-col items-start gap-2 rounded-lg border bg-[var(--bg-card)] p-4 text-left transition-colors hover:bg-[var(--bg-raised)]"
    >
      <span className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
        {scenario.family}
      </span>
      <span className="text-sm font-medium leading-snug">{scenario.title}</span>
      <span className="text-xs text-[var(--text-secondary)]">
        {scenario.difficulty} · {scenario.duration_minutes} min
      </span>
      {bestScore !== null && (
        <div className="mt-1 flex items-center gap-1.5 text-xs text-[var(--text-tertiary)]">
          <span>Your best:</span>
          <ScoreBadge score={bestScore} />
        </div>
      )}
    </button>
  );
}

export function ScenarioCardSkeleton() {
  return <div className="h-[104px] animate-pulse rounded-lg border bg-[var(--bg-card)]" />;
}
