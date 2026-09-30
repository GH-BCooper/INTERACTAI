"use client";

import { clsx } from "clsx";
import { TrendingDown, TrendingUp, TrendingUpDown } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { WeeklyVolumeChart } from "@/components/progress/weekly-volume-chart";
import { Sparkline } from "@/components/report/sparkline";
import { ScoreBadge } from "@/components/score/score-badge";
import { ButtonLink } from "@/components/ui/button";
import { capitalize, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { Segmented } from "@/components/ui/segmented";
import { useProgress } from "@/lib/api/hooks";

const ALL = "all";

function ProgressSkeleton() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6" aria-busy="true">
      <Skeleton className="h-7 w-40" />
      <div className="mt-4 flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-7 w-24 rounded-full" />
        ))}
      </div>
      <Skeleton className="mt-5 h-[74px] w-full rounded-lg" />
      <Skeleton className="mt-8 h-6 w-52" />
      <div className="mt-3 flex flex-col gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-[62px] w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="mt-8 h-40 w-full rounded-lg" />
    </div>
  );
}

export default function ProgressPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlFamily = searchParams.get("family") ?? undefined;
  const highlightCriterion = searchParams.get("criterion");
  const { data: progress, isPending, isPlaceholderData } = useProgress(urlFamily);

  // Arriving from the dashboard's "weakest criterion" link: bring that row into view.
  useEffect(() => {
    if (!highlightCriterion || !progress) return;
    document.getElementById(`criterion-${highlightCriterion}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlightCriterion, progress]);

  if (isPending || !progress) return <ProgressSkeleton />;

  const hasAnyData = progress.criterion_trends.length > 0 || progress.weekly_volume.length > 0;
  if (!hasAnyData && progress.families_attempted.length === 0) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 sm:px-6">
        <EmptyState
          icon={<TrendingUpDown size={18} />}
          title="No progress to show yet"
          body="Complete a couple of scored sessions in the same scenario family and your trends will show up here."
          action={
            <ButtonLink href="/app/scenarios" variant="primary" size="sm">
              Browse scenarios
            </ButtonLink>
          }
        />
      </div>
    );
  }

  function setFamily(family: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("family", family);
    params.delete("criterion");
    router.replace(`/app/progress?${params.toString()}`, { scroll: false });
  }

  const familyOptions = [
    { value: ALL, label: "All families" },
    ...progress.families_available.map((f) => ({ value: f, label: capitalize(f) })),
  ];

  return (
    <div className={clsx("mx-auto max-w-3xl px-4 py-8 transition-opacity duration-150 sm:px-6", isPlaceholderData && "opacity-60")}>
      <PageHeader title="Progress" />

      <Segmented className="mt-4" label="Filter by scenario family" value={progress.family} onChange={setFamily} options={familyOptions} />

      {progress.weakest_dimension && (
        <Card className="mt-5 flex items-start gap-3 p-4">
          {progress.weakest_dimension.trend < 0 ? (
            <TrendingDown size={18} className="mt-0.5 shrink-0 text-[var(--status-bad)]" aria-label="Declining" />
          ) : (
            <TrendingUp size={18} className="mt-0.5 shrink-0 text-[var(--status-ok)]" aria-label="Improving or steady" />
          )}
          <div>
            <p className="text-sm font-medium">{progress.weakest_dimension.name} needs the most attention</p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">{progress.weakest_dimension.next_action}</p>
          </div>
        </Card>
      )}

      <h2 className="mt-8 text-md font-medium">Score trend by criterion</h2>
      {progress.criterion_trends.length === 0 && (
        <p className="mt-2 text-sm text-[var(--text-secondary)]">Not enough scored sessions here yet to show a trend.</p>
      )}
      <div className="stagger mt-3 flex flex-col gap-3">
        {progress.criterion_trends.map((trend) => {
          const latest = trend.points.at(-1);
          const highlighted = trend.criterion_key === highlightCriterion;
          return (
            <Card
              key={trend.criterion_key}
              id={`criterion-${trend.criterion_key}`}
              className={clsx(
                "flex scroll-mt-24 flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between",
                highlighted && "border-[var(--accent)]",
              )}
            >
              <div>
                <p className="text-sm font-medium">{trend.name}</p>
                <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                  {trend.points.length} session{trend.points.length === 1 ? "" : "s"} scored
                </p>
              </div>
              <div className="flex items-center gap-3">
                {trend.points.length >= 2 ? (
                  <Sparkline
                    values={trend.points.map((p) => p.score)}
                    label={`${trend.name} across ${trend.points.length} sessions`}
                  />
                ) : (
                  // docs/ui-audit-2026-09.md §10: one point draws nothing — say why.
                  <span className="text-xs text-[var(--text-tertiary)]">1 session — need 2+ for a trend</span>
                )}
                <ScoreBadge score={latest?.score ?? null} />
              </div>
            </Card>
          );
        })}
      </div>

      <h2 className="mt-8 text-md font-medium">Practice volume by week</h2>
      <p className="mt-1 text-xs text-[var(--text-tertiary)]">Minutes, all families.</p>
      {progress.weekly_volume.length === 0 ? (
        <p className="mt-2 text-sm text-[var(--text-secondary)]">No sessions yet.</p>
      ) : (
        <Card className="mt-3 p-4">
          <WeeklyVolumeChart weeks={progress.weekly_volume} />
        </Card>
      )}

      <h2 className="mt-8 text-md font-medium">Scenario coverage</h2>
      <div className="mt-2 flex flex-wrap gap-2">
        {progress.families_attempted.map((f) => (
          <Link
            key={f}
            href={`/app/scenarios?family=${encodeURIComponent(f)}`}
            className="rounded-full border bg-[var(--bg-card)] px-3 py-1 text-xs text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-raised)]"
          >
            {capitalize(f)} — attempted
          </Link>
        ))}
        {progress.families_never_attempted.map((f) => (
          <Link
            key={f}
            href={`/app/scenarios?family=${encodeURIComponent(f)}`}
            className="rounded-full border border-dashed px-3 py-1 text-xs text-[var(--text-tertiary)] transition-colors hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)]"
          >
            {capitalize(f)} — not yet
          </Link>
        ))}
      </div>

      <h2 className="mt-8 text-md font-medium">Personal bests</h2>
      {progress.personal_bests.length === 0 ? (
        <p className="mt-2 text-sm text-[var(--text-secondary)]">Nothing scored yet here.</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {progress.personal_bests.map((best) => (
            <li key={best.criterion_key}>
              <Link
                href={`/app/sessions/${best.session_id}`}
                className="flex items-center justify-between rounded-lg border bg-[var(--bg-card)] px-4 py-2.5 text-sm transition-colors duration-150 hover:bg-[var(--bg-raised)]"
              >
                <span>{best.name}</span>
                <ScoreBadge score={best.score} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
