"use client";

import { AlertCircle, ArrowRight, Mic } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Sparkline } from "@/components/report/sparkline";
import { ScoreBadge } from "@/components/score/score-badge";
import { Button, ButtonLink, buttonClasses } from "@/components/ui/button";
import { LocalDate } from "@/components/ui/local-date";
import { Card, EmptyState, Skeleton } from "@/components/ui/primitives";
import { useDashboard, useMe, useScenarios } from "@/lib/api/hooks";
import type { Goal, ProgressStripOut, RecentSessionOut } from "@/lib/api/types";

import { StartSessionDialog } from "./start-session-dialog";

const GOAL_TO_FAMILY: Record<Goal, string> = {
  job_interview: "behavioural",
  technical_interview: "technical",
  salary_negotiation: "negotiation",
};

/** docs/ui-audit-2026-09.md §5: the empty state starts the first session right here — a gentle
 * scenario in the user's goal family, 5 minutes — instead of routing to the library. */
function EmptyDashboard({ goal }: { goal: Goal | null }) {
  const family = goal ? GOAL_TO_FAMILY[goal] : undefined;
  const { data: familyScenarios } = useScenarios(family ? { family, difficulty: "gentle" } : { difficulty: "gentle" });
  const { data: anyScenarios } = useScenarios();
  const scenario = familyScenarios?.[0] ?? anyScenarios?.[0] ?? null;
  const [open, setOpen] = useState(false);

  return (
    <div className="mx-auto max-w-lg px-4 py-16 sm:px-6">
      <EmptyState
        icon={<Mic size={18} />}
        title="Ready for your first session?"
        body={
          scenario ? (
            <>
              Start with <span className="text-[var(--text-primary)]">{scenario.title}</span>: a gentle, five-minute
              warm-up. You can change the difficulty and length before you begin.
            </>
          ) : (
            "Pick a scenario from the library, choose a difficulty and length, and start talking."
          )
        }
        action={
          <div className="flex flex-wrap justify-center gap-2">
            {scenario && (
              <Button variant="primary" onClick={() => setOpen(true)}>
                Start your first 5-minute session
              </Button>
            )}
            <ButtonLink href="/app/scenarios" variant={scenario ? "ghost" : "primary"}>
              Browse scenarios
            </ButtonLink>
          </div>
        }
      />
      {scenario && (
        <StartSessionDialog open={open} scenario={scenario} defaultMinutes={5} onClose={() => setOpen(false)} />
      )}
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6" aria-busy="true">
      <Skeleton className="h-7 w-56" />
      <Skeleton className="mt-4 h-[92px] w-full rounded-lg" />
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[92px] rounded-lg" />
        ))}
      </div>
      <Skeleton className="mt-8 h-6 w-40" />
      <div className="mt-3 flex flex-col gap-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-[62px] rounded-lg" />
        ))}
      </div>
      <span className="sr-only">Loading your dashboard…</span>
    </div>
  );
}

function recommendationHref(kind: string, sessionId: string | null, scenarioId: string | null): string {
  if (kind === "continue_session" && sessionId) return `/app/practice/${sessionId}`;
  if (scenarioId) return `/app/scenarios?scenario=${scenarioId}`;
  return "/app/scenarios";
}

function StatTile({ label, children, footer }: { label: string; children: React.ReactNode; footer?: React.ReactNode }) {
  return (
    <Card className="flex flex-col p-4">
      <p className="text-xs text-[var(--text-tertiary)]">{label}</p>
      <div className="mt-1 flex-1">{children}</div>
      {footer && <div className="mt-1 text-xs text-[var(--text-tertiary)]">{footer}</div>}
    </Card>
  );
}

function MinutesDelta({ strip }: { strip: ProgressStripOut }) {
  const diff = strip.total_minutes_this_week - strip.total_minutes_last_week;
  if (strip.total_minutes_last_week === 0 && strip.total_minutes_this_week === 0) return <>No practice yet this week</>;
  if (diff === 0) return <>Same as last week</>;
  return (
    <span className={diff > 0 ? "text-[var(--status-ok)]" : undefined}>
      {diff > 0 ? "+" : "−"}
      {Math.abs(diff)} min vs last week
    </span>
  );
}

function RecentSessionRow({ s }: { s: RecentSessionOut }) {
  return (
    <Link
      href={`/app/sessions/${s.id}`}
      className="flex items-center justify-between gap-3 rounded-lg border bg-[var(--bg-card)] px-4 py-3 text-sm transition-colors duration-150 hover:bg-[var(--bg-raised)]"
    >
      <div className="min-w-0">
        <p className="flex items-center gap-2 truncate">
          {!s.report_read && (
            <span className="h-2 w-2 shrink-0 rounded-full bg-[var(--accent)]" aria-label="Unread report" title="Unread report" />
          )}
          <span className="truncate">{s.scenario_title}</span>
        </p>
        <p className="text-xs text-[var(--text-tertiary)]">
          <LocalDate value={s.created_at} relative />
          {s.duration_ms ? ` · ${Math.max(1, Math.round(s.duration_ms / 60_000))} min` : ""}
        </p>
      </div>
      <ScoreBadge score={s.overall_score} />
    </Link>
  );
}

export function DashboardView() {
  const router = useRouter();
  const { data: me } = useMe();
  const { data: dashboard, isPending } = useDashboard();

  useEffect(() => {
    if (me && !me.user.onboarded_at) router.replace("/onboarding");
  }, [me, router]);

  // Oldest → newest, scored sessions only: the sparkline is a shape of real numbers, never a
  // gap filled in with a guess.
  const scoreHistory = useMemo(
    () =>
      [...(dashboard?.recent_sessions ?? [])]
        .reverse()
        .map((s) => s.overall_score)
        .filter((v): v is number => v !== null),
    [dashboard],
  );

  if (!me || !me.user.onboarded_at) return <DashboardSkeleton />;
  if (isPending || !dashboard) return <DashboardSkeleton />;

  const hasAnyHistory = dashboard.recent_sessions.length > 0;
  const isFreshUser = !hasAnyHistory && dashboard.recommendation.kind === "start_scenario";

  if (isFreshUser && dashboard.progress_strip.sessions_this_week === 0) {
    return <EmptyDashboard goal={me.profile?.goal ?? null} />;
  }

  const { recommendation, progress_strip: strip, recent_sessions, attention } = dashboard;
  const weakestHref = strip.weakest_criterion_key
    ? `/app/progress?${new URLSearchParams({
        ...(strip.weakest_criterion_family ? { family: strip.weakest_criterion_family } : {}),
        criterion: strip.weakest_criterion_key,
      }).toString()}`
    : null;

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <h1 className="text-lg font-medium">
        {me.user.name ? `Welcome back, ${me.user.name.split(" ")[0]}` : "Welcome back"}
      </h1>

      {/* Primary action block — the whole card is one link; the "button" is only its look. */}
      <Link
        href={recommendationHref(recommendation.kind, recommendation.session_id, recommendation.scenario_id)}
        className="group mt-4 flex flex-col gap-4 rounded-lg border bg-[var(--bg-card)] p-5 transition-colors duration-150 hover:bg-[var(--bg-raised)] sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <p className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
            {recommendation.kind === "continue_session" ? "Continue where you left off" : "Recommended next"}
          </p>
          <p className="mt-1 text-md font-medium">{recommendation.reason}</p>
        </div>
        <span aria-hidden className={buttonClasses({ variant: "primary", className: "shrink-0 self-start sm:self-auto" })}>
          {recommendation.kind === "continue_session" ? "Continue" : "Start"}
          <ArrowRight size={16} className="transition-transform duration-150 group-hover:translate-x-0.5" />
        </span>
      </Link>

      {/* Progress strip */}
      <div className="stagger mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Sessions this week">
          <p className="font-mono text-xl">{strip.sessions_this_week}</p>
        </StatTile>
        <StatTile label="Minutes this week" footer={<MinutesDelta strip={strip} />}>
          <p className="font-mono text-xl">{strip.total_minutes_this_week}</p>
        </StatTile>
        <StatTile
          label="Overall score"
          footer={
            strip.overall_score_delta !== null ? (
              <span className={strip.overall_score_delta >= 0 ? "text-[var(--status-ok)]" : "text-[var(--status-bad)]"}>
                {strip.overall_score_delta >= 0 ? "+" : "−"}
                {Math.abs(strip.overall_score_delta).toFixed(1)} vs previous session
              </span>
            ) : undefined
          }
        >
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
            <ScoreBadge score={strip.overall_score} />
            {scoreHistory.length >= 2 && <Sparkline values={scoreHistory} height={24} width={72} label="Overall score across your recent sessions" />}
          </div>
        </StatTile>
        <StatTile label="Weakest criterion">
          {weakestHref && strip.weakest_criterion_name ? (
            <Link href={weakestHref} className="group inline-flex items-center gap-1 text-sm font-medium hover:text-[var(--accent)]">
              {strip.weakest_criterion_name}
              <ArrowRight size={14} aria-hidden className="opacity-60 transition-transform duration-150 group-hover:translate-x-0.5" />
            </Link>
          ) : (
            <p className="text-sm font-medium">{strip.weakest_criterion_name ?? "—"}</p>
          )}
        </StatTile>
      </div>

      {/* Attention panel — at most one item */}
      {attention && (
        <Link
          href={
            attention.session_id
              ? `/app/sessions/${attention.session_id}`
              : attention.scenario_id
                ? `/app/scenarios/${attention.scenario_id}`
                : "/app/progress"
          }
          className="mt-4 flex items-center gap-3 rounded-lg border border-[var(--accent)]/40 bg-[var(--bg-card)] p-4 transition-colors duration-150 hover:bg-[var(--bg-raised)]"
        >
          <AlertCircle size={18} className="shrink-0 text-[var(--accent)]" />
          <p className="text-sm">{attention.text}</p>
        </Link>
      )}

      {/* Last five sessions */}
      <div className="mt-8 flex items-baseline justify-between">
        <h2 className="text-md font-medium">Last five sessions</h2>
        {hasAnyHistory && (
          <Link href="/app/sessions" className="text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
            View all
          </Link>
        )}
      </div>
      <div className="mt-3">
        {!hasAnyHistory ? (
          <EmptyState compact title="No sessions yet" body="Start the recommended session above to see it here." />
        ) : (
          <ul className="stagger flex flex-col gap-2">
            {recent_sessions.map((s) => (
              <li key={s.id}>
                <RecentSessionRow s={s} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
