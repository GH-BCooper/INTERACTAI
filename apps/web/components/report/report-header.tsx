"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { ScoreBadge } from "@/components/score/score-badge";
import { StartSessionDialog } from "@/components/dashboard/start-session-dialog";
import type { ScenarioOut, SessionOut, SessionScoreOut } from "@/lib/api/types";

function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  const totalMinutes = Math.round(ms / 60_000);
  return `${totalMinutes} min`;
}

/** Task 3.3b. "Share", "Export" and "Delete recording" are shown as disabled affordances, not
 * silently omitted or faked — no backend endpoint exists for any of the three yet (a genuine
 * gap, not an oversight; see docs/PROGRESS.md). "Practise again" and "Retry one question" both
 * have real backend support and work. */
export function ReportHeader({
  session,
  scenario,
  scores,
}: {
  session: SessionOut;
  scenario: ScenarioOut | undefined;
  scores: SessionScoreOut[];
}) {
  const [showPractiseAgain, setShowPractiseAgain] = useState(false);

  const { overall, avgPercentile } = useMemo(() => {
    const rubricScores = scores.filter((s) => s.criterion_key !== "delivery");
    const withScores = rubricScores.filter((s) => s.aggregate_score !== null);
    const overallValue =
      withScores.length > 0
        ? withScores.reduce((sum, s) => sum + s.aggregate_score!, 0) / withScores.length
        : null;
    const withPct = rubricScores.filter((s) => s.percentile_vs_self !== null);
    const pct =
      withPct.length > 0
        ? withPct.reduce((sum, s) => sum + s.percentile_vs_self!, 0) / withPct.length
        : null;
    return { overall: overallValue, avgPercentile: pct };
  }, [scores]);

  return (
    <div className="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h1 className="text-lg font-medium">{scenario?.title ?? "Practice session"}</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {scenario?.family} · {session.target_minutes} min target · {formatDuration(session.duration_ms)} actual ·{" "}
          {new Date(session.created_at).toLocaleDateString()}
        </p>
        {avgPercentile !== null && (
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            Better than {Math.round(avgPercentile * 100)}% of your own past sessions in this scenario family.
          </p>
        )}
      </div>

      <div className="flex flex-col items-start gap-3 sm:items-end">
        <div>
          <span className="text-xs text-[var(--text-tertiary)]">Overall</span>
          <div className="mt-0.5">
            <ScoreBadge score={overall} />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {scenario && (
            <Button variant="primary" size="sm" onClick={() => setShowPractiseAgain(true)}>
              Practise again
            </Button>
          )}
          <Button variant="secondary" size="sm" disabled title="Coming soon">
            Share
          </Button>
          <Button variant="secondary" size="sm" disabled title="Coming soon">
            Export
          </Button>
          <Button variant="ghost" size="sm" disabled title="Coming soon">
            Delete recording
          </Button>
        </div>
      </div>

      {showPractiseAgain && scenario && (
        <StartSessionDialog scenario={scenario} onClose={() => setShowPractiseAgain(false)} />
      )}
    </div>
  );
}
