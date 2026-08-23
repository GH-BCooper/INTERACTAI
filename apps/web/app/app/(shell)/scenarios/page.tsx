"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { ScenarioCard, ScenarioCardSkeleton } from "@/components/dashboard/scenario-card";
import { StartSessionDialog } from "@/components/dashboard/start-session-dialog";
import { useScenarioProgress, useScenarios } from "@/lib/api/hooks";
import type { ScenarioOut } from "@/lib/api/types";

const FAMILIES = ["all", "technical", "behavioural", "negotiation", "viva"] as const;
const DIFFICULTIES = ["all", "gentle", "standard", "hard"] as const;
const DURATIONS = ["all", "20", "30"] as const;

function readParam<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return value && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

export default function ScenarioLibraryPage() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [family, setFamily] = useState(() =>
    readParam(searchParams.get("family"), FAMILIES, "all"),
  );
  const [difficulty, setDifficulty] = useState(() =>
    readParam(searchParams.get("difficulty"), DIFFICULTIES, "all"),
  );
  const [duration, setDuration] = useState(() =>
    readParam(searchParams.get("duration"), DURATIONS, "all"),
  );
  const [tag, setTag] = useState(searchParams.get("tag") ?? "");

  function updateFilter(next: {
    family?: (typeof FAMILIES)[number];
    difficulty?: (typeof DIFFICULTIES)[number];
    duration?: (typeof DURATIONS)[number];
    tag?: string;
  }) {
    const nextFamily = next.family ?? family;
    const nextDifficulty = next.difficulty ?? difficulty;
    const nextDuration = next.duration ?? duration;
    const nextTag = next.tag ?? tag;
    if (next.family !== undefined) setFamily(next.family);
    if (next.difficulty !== undefined) setDifficulty(next.difficulty);
    if (next.duration !== undefined) setDuration(next.duration);
    if (next.tag !== undefined) setTag(next.tag);

    const params = new URLSearchParams();
    if (nextFamily !== "all") params.set("family", nextFamily);
    if (nextDifficulty !== "all") params.set("difficulty", nextDifficulty);
    if (nextDuration !== "all") params.set("duration", nextDuration);
    if (nextTag.trim()) params.set("tag", nextTag.trim());
    const qs = params.toString();
    router.replace(qs ? `/app/scenarios?${qs}` : "/app/scenarios");
  }

  const { data: scenarios, isPending } = useScenarios({
    family: family === "all" ? undefined : family,
    difficulty: difficulty === "all" ? undefined : difficulty,
    duration: duration === "all" ? undefined : Number(duration),
    tag: tag.trim() || undefined,
  });
  const { data: scenarioProgress } = useScenarioProgress();

  const preselectedId = searchParams.get("scenario");
  const [manualSelection, setManualSelection] = useState<ScenarioOut | null>(null);
  const preselected = useMemo(
    () => scenarios?.find((s) => s.id === preselectedId) ?? null,
    [scenarios, preselectedId],
  );
  const dialogScenario = manualSelection ?? preselected;

  function closeDialog() {
    setManualSelection(null);
    if (preselectedId) {
      const params = new URLSearchParams(searchParams.toString());
      params.delete("scenario");
      const qs = params.toString();
      router.replace(qs ? `/app/scenarios?${qs}` : "/app/scenarios");
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-lg font-medium">Scenario library</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Pick a scenario. You choose the difficulty and length when you start.
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <div className="flex gap-2" role="tablist" aria-label="Filter by scenario family">
          {FAMILIES.map((f) => (
            <button
              key={f}
              type="button"
              role="tab"
              aria-selected={family === f}
              onClick={() => updateFilter({ family: f })}
              className={`rounded-full border px-3 py-1 text-xs capitalize transition-colors ${
                family === f
                  ? "bg-[var(--accent)] text-[var(--text-on-accent)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        <select
          aria-label="Filter by difficulty"
          value={difficulty}
          onChange={(e) =>
            updateFilter({ difficulty: e.target.value as (typeof DIFFICULTIES)[number] })
          }
          className="rounded-md border bg-[var(--bg-card)] px-2 py-1.5 text-xs capitalize"
        >
          {DIFFICULTIES.map((d) => (
            <option key={d} value={d}>
              {d === "all" ? "Any difficulty" : d}
            </option>
          ))}
        </select>

        <select
          aria-label="Filter by duration"
          value={duration}
          onChange={(e) => updateFilter({ duration: e.target.value as (typeof DURATIONS)[number] })}
          className="rounded-md border bg-[var(--bg-card)] px-2 py-1.5 text-xs"
        >
          {DURATIONS.map((d) => (
            <option key={d} value={d}>
              {d === "all" ? "Any duration" : `${d} min`}
            </option>
          ))}
        </select>

        <input
          aria-label="Filter by tag"
          value={tag}
          onChange={(e) => updateFilter({ tag: e.target.value })}
          placeholder="Filter by tag…"
          className="w-40 rounded-md border bg-[var(--bg-card)] px-2 py-1.5 text-xs placeholder:text-[var(--text-tertiary)]"
        />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {isPending && Array.from({ length: 6 }).map((_, i) => <ScenarioCardSkeleton key={i} />)}
        {!isPending && scenarios?.length === 0 && (
          <div className="col-span-full rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm text-[var(--text-secondary)]">
              No scenarios match these filters — try widening them.
            </p>
          </div>
        )}
        {scenarios?.map((s) => (
          <ScenarioCard
            key={s.id}
            scenario={s}
            bestScore={scenarioProgress?.[s.id]?.best_score ?? null}
            onStart={() => setManualSelection(s)}
          />
        ))}

        {!isPending && (
          <a
            href="/app/scenarios/custom"
            className="flex flex-col items-start justify-center gap-1 rounded-lg border border-dashed bg-[var(--bg-card)] p-4 text-left text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)]"
          >
            <span className="text-sm font-medium">Custom scenario</span>
            <span className="text-xs">Author your own — coming soon</span>
          </a>
        )}
      </div>

      {dialogScenario && <StartSessionDialog scenario={dialogScenario} onClose={closeDialog} />}
    </div>
  );
}
