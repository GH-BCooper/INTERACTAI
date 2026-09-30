"use client";

import { Clock } from "lucide-react";

import { ScoreBadge } from "@/components/score/score-badge";
import { capitalize, DifficultyMeter, Skeleton } from "@/components/ui/primitives";
import type { PersonaOut, ScenarioOut } from "@/lib/api/types";

/** docs/ui-audit-2026-09.md §6: enough on the card to tell scenarios apart — the brief, who
 * you will talk to, the tags — not just family/title/difficulty. */
export function ScenarioCard({
  scenario,
  persona = null,
  onStart,
  bestScore = null,
}: {
  scenario: ScenarioOut;
  persona?: PersonaOut | null;
  onStart: () => void;
  bestScore?: number | null;
}) {
  return (
    <button
      type="button"
      onClick={onStart}
      className="group flex h-full flex-col items-start gap-2 rounded-lg border bg-[var(--bg-card)] p-4 text-left transition-colors duration-150 hover:border-[var(--text-tertiary)] hover:bg-[var(--bg-raised)]"
    >
      <div className="flex w-full items-center justify-between gap-2">
        <span className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">{capitalize(scenario.family)}</span>
        <DifficultyMeter difficulty={scenario.difficulty} />
      </div>
      <span className="text-sm font-medium leading-snug">{scenario.title}</span>
      <span className="line-clamp-2 text-xs leading-relaxed text-[var(--text-secondary)]">{scenario.brief}</span>

      {scenario.tags.length > 0 && (
        <span className="flex flex-wrap gap-1">
          {scenario.tags.slice(0, 3).map((t) => (
            <span key={t} className="rounded-full bg-[var(--bg-raised)] px-2 py-0.5 text-xs text-[var(--text-secondary)] group-hover:bg-[var(--bg-card)]">
              {t}
            </span>
          ))}
        </span>
      )}

      <span className="mt-auto flex w-full items-center justify-between gap-2 pt-2 text-xs text-[var(--text-tertiary)]">
        <span className="flex min-w-0 items-center gap-2">
          {persona && (
            <>
              <span
                aria-hidden
                className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-[var(--accent)] text-xs text-[var(--text-primary)]"
              >
                {persona.name.charAt(0)}
              </span>
              <span className="truncate">{persona.name}</span>
            </>
          )}
          <span className="flex shrink-0 items-center gap-1">
            <Clock size={12} aria-hidden /> {scenario.duration_minutes} min
          </span>
        </span>
        {bestScore !== null && (
          <span className="flex shrink-0 items-center gap-1.5">
            <span className="sr-only">Your best:</span>
            <ScoreBadge score={bestScore} />
          </span>
        )}
      </span>
    </button>
  );
}

export function ScenarioCardSkeleton() {
  return (
    <div className="flex h-[184px] flex-col gap-2 rounded-lg border bg-[var(--bg-card)] p-4" aria-hidden>
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-5/6" />
      <Skeleton className="mt-auto h-3 w-1/2" />
    </div>
  );
}
