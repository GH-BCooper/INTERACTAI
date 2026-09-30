"use client";

import { defaultFilter } from "cmdk";
import { Search, Wand2, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { ScenarioCard, ScenarioCardSkeleton } from "@/components/dashboard/scenario-card";
import { StartSessionDialog } from "@/components/dashboard/start-session-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";
import { capitalize, EmptyState, PageHeader, Pill } from "@/components/ui/primitives";
import { Segmented } from "@/components/ui/segmented";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { usePersonas, useScenarioProgress, useScenarios } from "@/lib/api/hooks";
import type { ScenarioOut } from "@/lib/api/types";

const FAMILIES = ["all", "technical", "behavioural", "negotiation", "viva"] as const;
const DIFFICULTIES = ["all", "gentle", "standard", "hard"] as const;
const DURATIONS = ["all", "20", "30"] as const;

type Family = (typeof FAMILIES)[number];
type DifficultyFilter = (typeof DIFFICULTIES)[number];
type DurationFilter = (typeof DURATIONS)[number];

function readParam<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return value && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

export default function ScenarioLibraryPage() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [family, setFamily] = useState<Family>(() => readParam(searchParams.get("family"), FAMILIES, "all"));
  const [difficulty, setDifficulty] = useState<DifficultyFilter>(() =>
    readParam(searchParams.get("difficulty"), DIFFICULTIES, "all"),
  );
  const [duration, setDuration] = useState<DurationFilter>(() => readParam(searchParams.get("duration"), DURATIONS, "all"));
  const [tag, setTag] = useState(searchParams.get("tag") ?? "");
  const [search, setSearch] = useState(searchParams.get("q") ?? "");
  // docs/ui-audit-2026-09.md §6: typing no longer rewrites the URL (and refetches) per keystroke.
  const debouncedTag = useDebouncedValue(tag.trim(), 250);
  const debouncedSearch = useDebouncedValue(search.trim(), 250);

  useEffect(() => {
    const params = new URLSearchParams();
    if (family !== "all") params.set("family", family);
    if (difficulty !== "all") params.set("difficulty", difficulty);
    if (duration !== "all") params.set("duration", duration);
    if (debouncedTag) params.set("tag", debouncedTag);
    if (debouncedSearch) params.set("q", debouncedSearch);
    const scenario = searchParams.get("scenario");
    if (scenario) params.set("scenario", scenario);
    const qs = params.toString();
    if (qs !== searchParams.toString()) router.replace(qs ? `/app/scenarios?${qs}` : "/app/scenarios", { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- URL mirrors the filters, not the reverse
  }, [family, difficulty, duration, debouncedTag, debouncedSearch]);

  const { data: scenarios, isPending } = useScenarios({
    family: family === "all" ? undefined : family,
    difficulty: difficulty === "all" ? undefined : difficulty,
    duration: duration === "all" ? undefined : Number(duration),
    tag: debouncedTag || undefined,
  });
  const { data: scenarioProgress } = useScenarioProgress();
  const { data: personas } = usePersonas();

  // Same fuzzy scorer the command palette uses (cmdk's), so "sys des" finds the same things in
  // both places. Best matches first.
  const visible = useMemo(() => {
    if (!scenarios) return undefined;
    if (!debouncedSearch) return scenarios;
    return scenarios
      .map((s) => ({ s, score: defaultFilter(`${s.title} ${s.brief} ${s.tags.join(" ")}`, debouncedSearch) }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .map((x) => x.s);
  }, [scenarios, debouncedSearch]);

  const preselectedId = searchParams.get("scenario");
  const [manualSelection, setManualSelection] = useState<ScenarioOut | null>(null);
  const preselected = useMemo(() => scenarios?.find((s) => s.id === preselectedId) ?? null, [scenarios, preselectedId]);
  const dialogScenario = manualSelection ?? preselected;

  function closeDialog() {
    setManualSelection(null);
    if (preselectedId) {
      const params = new URLSearchParams(searchParams.toString());
      params.delete("scenario");
      const qs = params.toString();
      router.replace(qs ? `/app/scenarios?${qs}` : "/app/scenarios", { scroll: false });
    }
  }

  const filtersActive = family !== "all" || difficulty !== "all" || duration !== "all" || tag !== "" || search !== "";

  function clearFilters() {
    setFamily("all");
    setDifficulty("all");
    setDuration("all");
    setTag("");
    setSearch("");
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader title="Scenario library" description="Pick a scenario. You choose the difficulty and length when you start." />

      <div className="mt-6 flex flex-col gap-3">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search size={14} aria-hidden className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" />
            <Input
              aria-label="Search scenarios"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search scenarios…"
              className="pl-9"
            />
          </div>
          <Input
            aria-label="Filter by tag"
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            placeholder="Filter by tag…"
            className="sm:w-48"
          />
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <Segmented
            label="Filter by scenario family"
            value={family}
            onChange={setFamily}
            options={FAMILIES.map((f) => ({ value: f, label: f === "all" ? "All families" : capitalize(f) }))}
          />
          <Segmented
            label="Filter by difficulty"
            value={difficulty}
            onChange={setDifficulty}
            options={DIFFICULTIES.map((d) => ({ value: d, label: d === "all" ? "Any difficulty" : capitalize(d) }))}
          />
          <Segmented
            label="Filter by duration"
            value={duration}
            onChange={setDuration}
            options={DURATIONS.map((d) => ({ value: d, label: d === "all" ? "Any length" : `${d} min` }))}
          />
          {filtersActive && (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              <X size={14} aria-hidden /> Clear
            </Button>
          )}
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {isPending && Array.from({ length: 6 }).map((_, i) => <ScenarioCardSkeleton key={i} />)}
        {!isPending && visible?.length === 0 && (
          <EmptyState
            className="col-span-full"
            compact
            title="No scenarios match"
            body="Try widening the filters or a different search."
            action={
              <Button variant="secondary" size="sm" onClick={clearFilters}>
                Clear filters
              </Button>
            }
          />
        )}
        {!isPending && visible && visible.length > 0 && (
          <>
            {visible.map((s) => (
              <div key={s.id} className="animate-rise-in">
                <ScenarioCard
                  scenario={s}
                  persona={personas?.find((p) => p.id === s.persona_id) ?? null}
                  bestScore={scenarioProgress?.[s.id]?.best_score ?? null}
                  onStart={() => setManualSelection(s)}
                />
              </div>
            ))}
          </>
        )}

        {/* docs/ui-audit-2026-09.md §6: authoring isn't built (POST /scenarios is 501), so this is
            shown as clearly unavailable rather than as a link to a dead end. */}
        {!isPending && !filtersActive && (
          <div
            aria-disabled="true"
            className="flex flex-col items-start justify-center gap-1 rounded-lg border border-dashed p-4 text-left text-[var(--text-tertiary)]"
          >
            <span className="flex items-center gap-2 text-sm font-medium text-[var(--text-secondary)]">
              <Wand2 size={14} aria-hidden /> Custom scenario <Pill tone="outline">Soon</Pill>
            </span>
            <span className="text-xs">Author your own brief, persona and rubric.</span>
          </div>
        )}
      </div>

      {dialogScenario && <StartSessionDialog key={dialogScenario.id} scenario={dialogScenario} onClose={closeDialog} />}
    </div>
  );
}
