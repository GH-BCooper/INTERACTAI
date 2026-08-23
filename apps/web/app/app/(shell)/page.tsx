"use client";

import { AlertCircle, ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ScoreBadge } from "@/components/score/score-badge";
import { Button } from "@/components/ui/button";
import { useDashboard, useMe } from "@/lib/api/hooks";

function EmptyDashboard() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-24 text-center">
      <h1 className="text-lg font-medium">Ready for your first session?</h1>
      <p className="text-sm text-[var(--text-secondary)]">
        Pick a scenario from the library, choose a difficulty and length, and start talking.
      </p>
      <a href="/app/scenarios">
        <Button variant="primary" size="md" className="mt-2">
          Browse scenarios
        </Button>
      </a>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="h-28 animate-pulse rounded-lg border bg-[var(--bg-card)]" />
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-lg border bg-[var(--bg-card)]" />
        ))}
      </div>
      <div className="mt-6 h-64 animate-pulse rounded-lg border bg-[var(--bg-card)]" />
    </div>
  );
}

function recommendationHref(kind: string, sessionId: string | null, scenarioId: string | null): string {
  if (kind === "continue_session" && sessionId) return `/app/practice/${sessionId}`;
  if (scenarioId) return `/app/scenarios?scenario=${scenarioId}`;
  return "/app/scenarios";
}

export default function DashboardPage() {
  const router = useRouter();
  const { data: me } = useMe();
  const { data: dashboard, isPending } = useDashboard();

  useEffect(() => {
    if (me && !me.user.onboarded_at) router.replace("/onboarding");
  }, [me, router]);

  if (!me || !me.user.onboarded_at) return <DashboardSkeleton />;
  if (isPending || !dashboard) return <DashboardSkeleton />;

  const hasAnyHistory = dashboard.recent_sessions.length > 0;
  const isFreshUser = !hasAnyHistory && dashboard.recommendation.kind === "start_scenario";

  if (isFreshUser && dashboard.progress_strip.sessions_this_week === 0) {
    return <EmptyDashboard />;
  }

  const { recommendation, progress_strip: strip, recent_sessions, attention } = dashboard;

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <h1 className="text-lg font-medium">
        {me?.user.name ? `Welcome back, ${me.user.name.split(" ")[0]}` : "Welcome back"}
      </h1>

      {/* Primary action block */}
      <a
        href={recommendationHref(recommendation.kind, recommendation.session_id, recommendation.scenario_id)}
        className="mt-4 flex items-center justify-between rounded-lg border bg-[var(--bg-card)] p-5 transition-colors hover:bg-[var(--bg-raised)]"
      >
        <div>
          <p className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
            {recommendation.kind === "continue_session" ? "Continue where you left off" : "Recommended next"}
          </p>
          <p className="mt-1 text-md font-medium">{recommendation.reason}</p>
        </div>
        <Button variant="primary" size="md" className="shrink-0">
          {recommendation.kind === "continue_session" ? "Continue" : "Start"}
          <ArrowRight size={16} />
        </Button>
      </a>

      {/* Progress strip */}
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border bg-[var(--bg-card)] p-4">
          <p className="text-xs text-[var(--text-tertiary)]">Sessions this week</p>
          <p className="mt-1 font-mono text-xl">{strip.sessions_this_week}</p>
        </div>
        <div className="rounded-lg border bg-[var(--bg-card)] p-4">
          <p className="text-xs text-[var(--text-tertiary)]">Minutes this week</p>
          <p className="mt-1 font-mono text-xl">{strip.total_minutes_this_week}</p>
        </div>
        <div className="rounded-lg border bg-[var(--bg-card)] p-4">
          <p className="text-xs text-[var(--text-tertiary)]">Overall score</p>
          <div className="mt-1.5 flex items-center gap-2">
            <ScoreBadge score={strip.overall_score} />
            {strip.overall_score_delta !== null && (
              <span
                className={`font-mono text-xs ${strip.overall_score_delta >= 0 ? "text-[var(--score-strong)]" : "text-[var(--score-weak)]"}`}
              >
                {strip.overall_score_delta >= 0 ? "+" : ""}
                {strip.overall_score_delta.toFixed(1)}
              </span>
            )}
          </div>
        </div>
        <div className="rounded-lg border bg-[var(--bg-card)] p-4">
          <p className="text-xs text-[var(--text-tertiary)]">Weakest criterion</p>
          <p className="mt-1 text-sm font-medium">{strip.weakest_criterion_name ?? "—"}</p>
        </div>
      </div>

      {/* Attention panel — at most one item */}
      {attention && (
        <a
          href={
            attention.session_id
              ? `/app/sessions/${attention.session_id}`
              : attention.scenario_id
                ? `/app/scenarios/${attention.scenario_id}`
                : "/app/progress"
          }
          className="mt-4 flex items-center gap-3 rounded-lg border border-[var(--accent)]/40 bg-[var(--bg-card)] p-4 transition-colors hover:bg-[var(--bg-raised)]"
        >
          <AlertCircle size={18} className="shrink-0 text-[var(--accent)]" />
          <p className="text-sm">{attention.text}</p>
        </a>
      )}

      {/* Last five sessions */}
      <h2 className="mt-8 text-md font-medium">Last five sessions</h2>
      <div className="mt-3">
        {!hasAnyHistory && (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm text-[var(--text-secondary)]">
              You haven&apos;t practised yet — pick a scenario above to start your first session.
            </p>
          </div>
        )}
        {hasAnyHistory && (
          <ul className="flex flex-col gap-2">
            {recent_sessions.map((s) => (
              <li key={s.id}>
                <a
                  href={`/app/sessions/${s.id}`}
                  className="flex items-center justify-between rounded-lg border bg-[var(--bg-card)] px-4 py-3 text-sm hover:bg-[var(--bg-raised)]"
                >
                  <div>
                    <p>{s.scenario_title}</p>
                    <p className="text-xs text-[var(--text-tertiary)]">
                      {new Date(s.created_at).toLocaleDateString()}
                      {s.duration_ms ? ` · ${Math.round(s.duration_ms / 60_000)} min` : ""}
                      {!s.report_read ? " · unread" : ""}
                    </p>
                  </div>
                  <ScoreBadge score={s.overall_score} />
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
