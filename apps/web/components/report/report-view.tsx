"use client";

import { FileQuestion, Mic } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api/client";
import {
  usePersonas,
  useScenario,
  useSession,
  useSessionRecording,
  useSessionReport,
  useSessionScores,
  useSessionTurns,
} from "@/lib/api/hooks";
import { useReportWaveform } from "@/hooks/use-report-waveform";
import { PersonaAudioCache } from "@/lib/report/persona-audio-cache";
import { usePlayerStore } from "@/stores/player-store";
import { ButtonLink } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/primitives";

import { DeliveryPanel } from "./delivery-panel";
import { ReportHeader } from "./report-header";
import { ScorePanel } from "./score-panel";
import { Transcript } from "./transcript";
import { ScoringInProgress, VerdictBlock } from "./verdict-block";
import { Waveform } from "./waveform";

function SkeletonBlock({ heightClass }: { heightClass: string }) {
  return <Skeleton className={`w-full rounded-lg ${heightClass}`} />;
}

const SECTIONS = [
  { id: "verdict", label: "Verdict" },
  { id: "scores", label: "Scores" },
  { id: "delivery", label: "Delivery" },
  { id: "transcript", label: "Transcript" },
];

/** docs/ui-audit-2026-09.md §9: jump links, kept in the sticky player bar. */
function SectionNav() {
  return (
    <nav aria-label="Report sections" className="flex gap-1 overflow-x-auto text-xs">
      {SECTIONS.map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          className="whitespace-nowrap rounded-full px-2.5 py-1 text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-raised)] hover:text-[var(--text-primary)]"
        >
          {s.label}
        </a>
      ))}
    </nav>
  );
}

/** Task 3.3/3.4 — the report's client half. app/app/(shell)/sessions/[id]/page.tsx is the thin
 * Server Component shell; every field here needs authenticated data, which (per this project's
 * bearer-token-in-memory auth model, see docs/decisions/0015) is fetched client-side through
 * TanStack Query rather than in the Server Component itself. */
export function ReportView({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const { data: session, error: sessionError } = useSession(sessionId);
  const { data: scenario } = useScenario(session?.scenario_id);
  const { data: personas } = usePersonas();
  const sessionEnded = session?.status === "closing" || session?.status === "closed";
  const { data: report, error: reportError } = useSessionReport(sessionId, {
    pollWhilePending: true,
    enabled: sessionEnded,
  });
  // A 404 on the report means "the coach hasn't written it yet" (hooks.ts keeps retrying it).
  const reportPending =
    (reportError instanceof ApiError && reportError.status === 404) ||
    (report === undefined && sessionEnded);
  // Only once the session itself has loaded: for an unknown id these would each 404 too.
  const loadedId = session ? sessionId : undefined;
  const { data: turns } = useSessionTurns(loadedId);
  const { data: scores } = useSessionScores(loadedId);
  const { data: recording } = useSessionRecording(loadedId);

  const playheadMs = usePlayerStore((s) => s.playheadMs);
  const setPlayheadMs = usePlayerStore((s) => s.setPlayheadMs);
  const activeCriterion = usePlayerStore((s) => s.activeCriterion);
  const setActiveCriterion = usePlayerStore((s) => s.setActiveCriterion);

  const persona = useMemo(
    () => personas?.find((p) => p.id === scenario?.persona_id) ?? null,
    [personas, scenario],
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const waveform = useReportWaveform({
    containerRef,
    url: recording?.url ?? null,
    peaks: recording?.peaks ?? null,
    durationMs: recording?.duration_ms ?? session?.duration_ms ?? null,
    turns,
    highlightTurnId: report?.highlight_turn_id ?? null,
    lowlightTurnId: report?.lowlight_turn_id ?? null,
  });

  // Task 3.4g: deep-linked view state, restored once on mount and kept in sync afterwards.
  const restoredRef = useRef(false);
  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    const t = searchParams.get("t");
    const criterion = searchParams.get("criterion");
    if (t && Number.isFinite(Number(t))) setPlayheadMs(Number(t));
    if (criterion) setActiveCriterion(criterion);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- read once, intentionally
  }, []);

  useEffect(() => {
    if (!waveform.isReady) return;
    const t = searchParams.get("t");
    if (t && Number.isFinite(Number(t))) waveform.seekToMs(Number(t));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires once when the waveform becomes ready
  }, [waveform.isReady]);

  useEffect(() => {
    if (sessionError) return; // nothing to deep-link into
    const timer = setTimeout(() => {
      const params = new URLSearchParams();
      const turn = (turns ?? []).find((t) => playheadMs >= t.start_ms && playheadMs < t.end_ms);
      if (turn) params.set("turn", String(turn.index));
      params.set("t", String(Math.round(playheadMs)));
      if (activeCriterion) params.set("criterion", activeCriterion);
      router.replace(`?${params.toString()}`, { scroll: false });
    }, 300);
    return () => clearTimeout(timer);
  }, [playheadMs, activeCriterion, turns, router, sessionError]);

  const [audioCache] = useState(() => new PersonaAudioCache(sessionId));
  useEffect(() => () => audioCache.dispose(), [audioCache]);

  if (sessionError instanceof ApiError && (sessionError.status === 404 || sessionError.status === 403)) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 sm:px-6">
        <EmptyState
          icon={<FileQuestion size={18} />}
          title="We couldn't find this report"
          body="It may have been deleted, or it belongs to a different account."
          action={
            <ButtonLink href="/app/sessions" variant="primary" size="sm">
              Go to session history
            </ButtonLink>
          }
        />
      </div>
    );
  }

  if (session && (session.status === "created" || session.status === "active")) {
    return (
      <div className="mx-auto max-w-lg px-4 py-16 sm:px-6">
        <EmptyState
          icon={<Mic size={18} />}
          title="This session hasn't finished yet"
          body="The report is written once the session ends. Pick up where you left off, or end it from the practice room."
          action={
            <ButtonLink href={`/app/practice/${session.id}`} variant="primary" size="sm">
              Continue the session
            </ButtonLink>
          }
        />
      </div>
    );
  }

  const annotatableCriteria = (scores ?? [])
    .filter((s) => s.criterion_key !== "delivery")
    .map((s) => ({ key: s.criterion_key, name: s.name, anchor_descriptors: s.anchor_descriptors }));

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8 px-4 py-8 sm:px-6">
      {session ? (
        <ReportHeader session={session} scenario={scenario} scores={scores ?? []} />
      ) : (
        <SkeletonBlock heightClass="h-24" />
      )}

      {/* Sticky mini-player (docs/ui-audit-2026-09.md §9): the waveform controls and the section
          jump links stay reachable while reading the transcript. The shell's `main` scrolls. */}
      <div className="z-20 -mx-4 border-b bg-[var(--bg-page)]/95 px-4 pb-3 pt-2 backdrop-blur sm:sticky sm:top-0 sm:-mx-6 sm:px-6">
        {turns ? (
          <Waveform
            containerRef={containerRef}
            waveform={waveform}
            url={recording?.url ?? null}
            peaks={recording?.peaks ?? null}
            durationMs={recording?.duration_ms ?? session?.duration_ms ?? null}
            turns={turns}
            lowlightTurnId={report?.lowlight_turn_id ?? null}
          />
        ) : (
          <SkeletonBlock heightClass="h-24" />
        )}
        <div className="mt-2">
          <SectionNav />
        </div>
      </div>

      <section id="verdict" aria-label="Verdict" className="scroll-mt-48">
        {report ? (
          <VerdictBlock
            report={report}
            onSeekMs={waveform.seekToMs}
            turnStartMs={(turnId) => (turns ?? []).find((t) => t.id === turnId)?.start_ms ?? null}
          />
        ) : reportPending ? (
          <ScoringInProgress />
        ) : (
          <SkeletonBlock heightClass="h-32" />
        )}
      </section>

      <section id="scores" className="scroll-mt-48">
        <h2 className="text-md font-medium">Scores</h2>
        <div className="mt-3">
          {scores ? (
            <ScorePanel
              scores={scores}
              turns={turns ?? []}
              activeCriterion={activeCriterion}
              onSelectCriterion={setActiveCriterion}
            />
          ) : (
            <SkeletonBlock heightClass="h-48" />
          )}
        </div>
      </section>

      <section id="delivery" className="scroll-mt-48">
        <h2 className="text-md font-medium">Delivery</h2>
        <p className="mt-1 text-xs text-[var(--text-tertiary)]">
          Deterministic, from the transcript and timestamps — not a model judgement.
        </p>
        <div className="mt-3">
          {turns ? (
            <DeliveryPanel turns={turns} sessionDurationMs={session?.duration_ms ?? null} />
          ) : (
            <SkeletonBlock heightClass="h-24" />
          )}
        </div>
      </section>

      <section id="transcript" className="scroll-mt-48">
        <h2 className="text-md font-medium">Transcript</h2>
        <div className="mt-3">
          {turns ? (
            <Transcript
              turns={turns}
              sessionId={sessionId}
              onSeekMs={waveform.seekToMs}
              annotatableCriteria={annotatableCriteria}
              personaAudioCache={audioCache}
              personaVoiceId={persona?.voice_id ?? null}
            />
          ) : (
            <SkeletonBlock heightClass="h-64" />
          )}
        </div>
      </section>
    </div>
  );
}
