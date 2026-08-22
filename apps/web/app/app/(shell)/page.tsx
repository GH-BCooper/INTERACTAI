"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { ScenarioCard, ScenarioCardSkeleton } from "@/components/dashboard/scenario-card";
import { StartSessionDialog } from "@/components/dashboard/start-session-dialog";
import { useScenarios, useSessions } from "@/lib/api/hooks";
import type { ScenarioOut } from "@/lib/api/types";

const FAMILIES = ["all", "technical", "behavioural", "negotiation", "viva"] as const;

function EmptyRecentSessions() {
  return (
    <div className="rounded-lg border border-dashed p-6 text-center">
      <p className="text-sm text-[var(--text-secondary)]">
        You haven&apos;t practiced yet — pick a scenario above to start your first session.
      </p>
    </div>
  );
}

export default function DashboardPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [family, setFamily] = useState<(typeof FAMILIES)[number]>("all");

  const { data: scenarios, isPending } = useScenarios(family === "all" ? undefined : { family });
  const { data: recent } = useSessions({ limit: 5 });

  const preselectedId = searchParams.get("scenario");
  const [manualSelection, setManualSelection] = useState<ScenarioOut | null>(null);

  const preselected = useMemo(
    () => scenarios?.find((s) => s.id === preselectedId) ?? null,
    [scenarios, preselectedId],
  );
  const dialogScenario = manualSelection ?? preselected;

  function closeDialog() {
    setManualSelection(null);
    if (preselectedId) router.replace("/app");
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="text-lg font-medium">Practice library</h1>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Pick a scenario. You choose the difficulty and length when you start.
      </p>

      <div className="mt-6 flex gap-2" role="tablist" aria-label="Filter by scenario family">
        {FAMILIES.map((f) => (
          <button
            key={f}
            type="button"
            role="tab"
            aria-selected={family === f}
            onClick={() => setFamily(f)}
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

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {isPending &&
          Array.from({ length: 6 }).map((_, i) => <ScenarioCardSkeleton key={i} />)}
        {!isPending && scenarios?.length === 0 && (
          <p className="col-span-full text-sm text-[var(--text-secondary)]">
            No scenarios match this filter yet.
          </p>
        )}
        {scenarios?.map((s) => (
          <ScenarioCard key={s.id} scenario={s} onStart={() => setManualSelection(s)} />
        ))}
      </div>

      <h2 className="mt-10 text-md font-medium">Recent sessions</h2>
      <div className="mt-3">
        {recent && recent.items.length === 0 && <EmptyRecentSessions />}
        {recent && recent.items.length > 0 && (
          <ul className="flex flex-col gap-2">
            {recent.items.map((s) => (
              <li key={s.id}>
                <a
                  href={s.status === "closed" ? `/app/sessions/${s.id}` : `/app/practice/${s.id}`}
                  className="flex items-center justify-between rounded-lg border bg-[var(--bg-card)] px-4 py-3 text-sm hover:bg-[var(--bg-raised)]"
                >
                  <span>{new Date(s.created_at).toLocaleString()}</span>
                  <span className="text-xs uppercase text-[var(--text-tertiary)]">{s.status}</span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>

      {dialogScenario && <StartSessionDialog scenario={dialogScenario} onClose={closeDialog} />}
    </div>
  );
}
