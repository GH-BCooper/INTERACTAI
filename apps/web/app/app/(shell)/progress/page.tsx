"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { useSearchParams, useRouter } from "next/navigation";

import { Sparkline } from "@/components/report/sparkline";
import { ScoreBadge } from "@/components/score/score-badge";
import { useProgress } from "@/lib/api/hooks";

function ProgressSkeleton() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="h-8 w-48 animate-pulse rounded bg-[var(--bg-card)]" />
      <div className="mt-6 h-40 animate-pulse rounded-lg border bg-[var(--bg-card)]" />
    </div>
  );
}

function EmptyProgress() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-24 text-center">
      <h1 className="text-lg font-medium">No progress to show yet</h1>
      <p className="text-sm text-[var(--text-secondary)]">
        Complete a few sessions in the same scenario family and your trends will show up here.
      </p>
      <a href="/app/scenarios" className="mt-2 text-sm text-[var(--accent)] hover:text-[var(--accent-hover)]">
        Browse scenarios
      </a>
    </div>
  );
}

export default function ProgressPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlFamily = searchParams.get("family") ?? undefined;
  const { data: progress, isPending } = useProgress(urlFamily);

  if (isPending || !progress) return <ProgressSkeleton />;

  const hasAnyData = progress.criterion_trends.length > 0 || progress.weekly_volume.length > 0;
  if (!hasAnyData && progress.families_attempted.length === 0) return <EmptyProgress />;

  function setFamily(family: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("family", family);
    router.replace(`/app/progress?${params.toString()}`);
  }

  const maxWeeklyMinutes = Math.max(1, ...progress.weekly_volume.map((w) => w.minutes));

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <h1 className="text-lg font-medium">Progress</h1>

      <div className="mt-4 flex gap-2" role="tablist" aria-label="Filter by scenario family">
        {progress.families_available.map((f) => (
          <button
            key={f}
            type="button"
            role="tab"
            aria-selected={progress.family === f}
            onClick={() => setFamily(f)}
            className={`rounded-full border px-3 py-1 text-xs capitalize transition-colors ${
              progress.family === f
                ? "bg-[var(--accent)] text-[var(--text-on-accent)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {progress.weakest_dimension && (
        <div className="mt-5 flex items-start gap-3 rounded-lg border bg-[var(--bg-card)] p-4">
          {progress.weakest_dimension.trend < 0 ? (
            <TrendingDown size={18} className="mt-0.5 shrink-0 text-[var(--score-weak)]" />
          ) : (
            <TrendingUp size={18} className="mt-0.5 shrink-0 text-[var(--score-strong)]" />
          )}
          <div>
            <p className="text-sm font-medium">{progress.weakest_dimension.name} needs the most attention</p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">{progress.weakest_dimension.next_action}</p>
          </div>
        </div>
      )}

      <h2 className="mt-8 text-md font-medium">Score trend by criterion</h2>
      {progress.criterion_trends.length === 0 && (
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          Not enough sessions in this family yet to show a trend.
        </p>
      )}
      <div className="mt-3 flex flex-col gap-3">
        {progress.criterion_trends.map((trend) => {
          const latest = trend.points.at(-1);
          return (
            <div key={trend.criterion_key} className="flex items-center justify-between gap-4 rounded-lg border bg-[var(--bg-card)] p-3">
              <div>
                <p className="text-sm font-medium">{trend.name}</p>
                <p className="mt-0.5 text-xs text-[var(--text-tertiary)]">{trend.points.length} sessions scored</p>
              </div>
              <div className="flex items-center gap-3">
                <Sparkline values={trend.points.map((p) => p.score)} />
                <ScoreBadge score={latest?.score ?? null} />
              </div>
            </div>
          );
        })}
      </div>

      <h2 className="mt-8 text-md font-medium">Practice volume by week</h2>
      {progress.weekly_volume.length === 0 && (
        <p className="mt-2 text-sm text-[var(--text-secondary)]">No sessions yet.</p>
      )}
      <div className="mt-3 flex items-end gap-1.5" style={{ height: 80 }}>
        {progress.weekly_volume.map((w) => (
          <div key={w.week_start} className="flex flex-1 flex-col items-center gap-1" title={`${w.minutes} min, ${w.sessions} session(s)`}>
            <div
              className="w-full rounded-t bg-[var(--accent)]"
              style={{ height: `${Math.max(4, (w.minutes / maxWeeklyMinutes) * 64)}px` }}
            />
            <span className="text-[10px] text-[var(--text-tertiary)]">
              {new Date(w.week_start).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
            </span>
          </div>
        ))}
      </div>

      <h2 className="mt-8 text-md font-medium">Scenario coverage</h2>
      <div className="mt-2 flex flex-wrap gap-2">
        {progress.families_attempted.map((f) => (
          <span key={f} className="rounded-full border bg-[var(--bg-card)] px-3 py-1 text-xs capitalize text-[var(--text-primary)]">
            {f} — attempted
          </span>
        ))}
        {progress.families_never_attempted.map((f) => (
          <span key={f} className="rounded-full border border-dashed px-3 py-1 text-xs capitalize text-[var(--text-tertiary)]">
            {f} — not yet
          </span>
        ))}
      </div>

      <h2 className="mt-8 text-md font-medium">Personal bests</h2>
      {progress.personal_bests.length === 0 ? (
        <p className="mt-2 text-sm text-[var(--text-secondary)]">Nothing scored yet in this family.</p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {progress.personal_bests.map((best) => (
            <li key={best.criterion_key}>
              <a
                href={`/app/sessions/${best.session_id}`}
                className="flex items-center justify-between rounded-lg border bg-[var(--bg-card)] px-4 py-2.5 text-sm hover:bg-[var(--bg-raised)]"
              >
                <span>{best.name}</span>
                <ScoreBadge score={best.score} />
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
