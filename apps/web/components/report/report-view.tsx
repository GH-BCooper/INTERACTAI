"use client";

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

import { DeliveryPanel } from "./delivery-panel";
import { ReportHeader } from "./report-header";
import { ScorePanel } from "./score-panel";
import { Transcript } from "./transcript";
import { VerdictBlock } from "./verdict-block";
import { Waveform } from "./waveform";

function SkeletonBlock({ heightClass }: { heightClass: string }) {
  return <div className={`animate-pulse rounded-lg border bg-[var(--bg-card)] ${heightClass}`} />;
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
  const { data: report } = useSessionReport(sessionId, { pollWhilePending: true });
  const { data: turns } = useSessionTurns(sessionId);
  const { data: scores } = useSessionScores(sessionId);
  const { data: recording } = useSessionRecording(sessionId);

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
    const timer = setTimeout(() => {
      const params = new URLSearchParams();
      const turn = (turns ?? []).find((t) => playheadMs >= t.start_ms && playheadMs < t.end_ms);
      if (turn) params.set("turn", String(turn.index));
      params.set("t", String(Math.round(playheadMs)));
      if (activeCriterion) params.set("criterion", activeCriterion);
      router.replace(`?${params.toString()}`, { scroll: false });
    }, 300);
    return () => clearTimeout(timer);
  }, [playheadMs, activeCriterion, turns, router]);

  const [audioCache] = useState(() => new PersonaAudioCache(sessionId));
  useEffect(() => () => audioCache.dispose(), [audioCache]);

  if (sessionError instanceof ApiError && (sessionError.status === 404 || sessionError.status === 403)) {
    return <div className="p-8 text-center text-sm text-[var(--text-secondary)]">Report not found.</div>;
  }

  const annotatableCriteria = (scores ?? [])
    .filter((s) => s.criterion_key !== "delivery")
    .map((s) => ({ key: s.criterion_key, name: s.name, anchor_descriptors: s.anchor_descriptors }));

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8 px-6 py-8">
      {session ? (
        <ReportHeader session={session} scenario={scenario} scores={scores ?? []} />
      ) : (
        <SkeletonBlock heightClass="h-24" />
      )}

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

      {report ? (
        <VerdictBlock
          report={report}
          onSeekMs={waveform.seekToMs}
          turnStartMs={(turnId) => (turns ?? []).find((t) => t.id === turnId)?.start_ms ?? null}
        />
      ) : (
        <SkeletonBlock heightClass="h-32" />
      )}

      <section>
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

      <section>
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

      <section>
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
