"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { DeliveryPanel } from "@/components/report/delivery-panel";
import { ReportHeader } from "@/components/report/report-header";
import { ScorePanel } from "@/components/report/score-panel";
import { Transcript } from "@/components/report/transcript";
import { VerdictBlock } from "@/components/report/verdict-block";
import { Waveform } from "@/components/report/waveform";
import { Button } from "@/components/ui/button";
import { useReportWaveform } from "@/hooks/use-report-waveform";
import type {
  RecordingOut,
  ReportOut,
  ScenarioOut,
  SessionOut,
  SessionScoreOut,
  TurnOut,
} from "@/lib/api/types";
import { mapCharOffsetToMs } from "@/lib/report/map-char-offset-to-ms";
import { usePlayerStore } from "@/stores/player-store";

export interface DemoBundle {
  provenance: {
    session_id: string;
    recorded_at: string;
    host_class: string | null;
    persona_model: string | null;
    scorer_model_version: string | null;
    voices: { user: string; persona: string };
    note: string;
  };
  session: SessionOut;
  scenario: ScenarioOut;
  turns: TurnOut[];
  scores: SessionScoreOut[];
  report: ReportOut;
  recording: RecordingOut;
  latency_by_turn: Record<string, Record<string, number>>;
}

type TourStep = "idle" | "conversation" | "report" | "done";

// The tour's evidence moment: the strongest answer's specificity evidence, played back from the
// exact character offset the scorer cited (verified server-side by exact substring match).
const TOUR_CRITERION = "specificity";
const CONVERSATION_MS = 40_000;
const EVIDENCE_PLAY_MS = 9_000;

/** Phase 6 TASK 6.5 — the model-free demo. Every panel below is the real report component the
 * signed-in report uses (components/report/*), fed a static bundle exported from a real session
 * instead of TanStack Query. No account, no API, no realtime, no coach. */
export function DemoReport({ bundle }: { bundle: DemoBundle }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const scoresRef = useRef<HTMLElement>(null);
  const activeCriterion = usePlayerStore((s) => s.activeCriterion);
  const setActiveCriterion = usePlayerStore((s) => s.setActiveCriterion);
  const [step, setStep] = useState<TourStep>("idle");
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const waveform = useReportWaveform({
    containerRef,
    url: bundle.recording.url,
    peaks: bundle.recording.peaks,
    durationMs: bundle.recording.duration_ms,
    turns: bundle.turns,
    highlightTurnId: bundle.report.highlight_turn_id,
    lowlightTurnId: bundle.report.lowlight_turn_id,
  });

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  // The waveform hook exposes play/pause as one toggle; timers need the latest `isPlaying`.
  const waveformRef = useRef(waveform);
  waveformRef.current = waveform;
  const play = () => {
    if (!waveformRef.current.isPlaying) waveformRef.current.playPause();
  };
  const pause = () => {
    if (waveformRef.current.isPlaying) waveformRef.current.playPause();
  };

  const evidenceMs = useMemo(() => {
    for (const turn of bundle.turns) {
      const score = turn.scores.find((s) => s.criterion_key === TOUR_CRITERION && s.score !== null && s.score >= 4);
      const span = score?.evidence_spans[0];
      if (!span) continue;
      const offset = mapCharOffsetToMs(turn.text, turn.word_timings, span.start);
      if (offset !== null) return turn.start_ms + offset;
    }
    return null;
  }, [bundle.turns]);

  function startTour() {
    timers.current.forEach(clearTimeout);
    setStep("conversation");
    setActiveCriterion(null);
    waveform.seekToMs(0);
    play();
    timers.current = [
      setTimeout(() => {
        pause();
        setStep("report");
        setActiveCriterion(TOUR_CRITERION);
        scoresRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        if (evidenceMs !== null) {
          waveformRef.current.seekToMs(evidenceMs);
          play();
        }
      }, CONVERSATION_MS),
      setTimeout(() => {
        pause();
        setStep("done");
      }, CONVERSATION_MS + EVIDENCE_PLAY_MS),
    ];
  }

  const userTurns = bundle.turns.filter((t) => t.speaker === "user");

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-8 px-6 py-8">
      <div className="flex flex-col gap-3 rounded-lg border bg-[var(--bg-card)] p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-sm">
          <div className="font-medium">Sample session — no account, no models running</div>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {bundle.provenance.note} Recorded {bundle.provenance.recorded_at.slice(0, 10)} on {bundle.provenance.host_class ?? "an unrecorded host"} · persona{" "}
            {bundle.provenance.persona_model ?? "—"} · scorer {bundle.provenance.scorer_model_version ?? "—"}.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button onClick={startTour} disabled={!waveform.isReady}>
            {step === "idle" || step === "done" ? "Play the 60-second tour" : "Restart tour"}
          </Button>
          <Link href="/" className="inline-flex h-10 items-center rounded-md px-3 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
            Home
          </Link>
        </div>
      </div>

      {step !== "idle" && (
        <p aria-live="polite" className="-mt-4 text-xs text-[var(--text-secondary)]">
          {step === "conversation" && "1 / 2 · The conversation, as it was heard. A vague answer, then a follow-up that makes the candidate get specific."}
          {step === "report" && "2 / 2 · The report. Specificity is selected; the audio is now playing the exact moment the evidence span points at."}
          {step === "done" && "That's the loop: speak, be answered, be scored — with every score tied to words you actually said."}
        </p>
      )}

      <ReportHeader session={bundle.session} scenario={bundle.scenario} scores={bundle.scores} readOnly />

      <Waveform
        containerRef={containerRef}
        waveform={waveform}
        url={bundle.recording.url}
        peaks={bundle.recording.peaks}
        durationMs={bundle.recording.duration_ms}
        turns={bundle.turns}
        lowlightTurnId={bundle.report.lowlight_turn_id}
      />

      <section>
        <h2 className="text-md font-medium">Response latency, measured</h2>
        <p className="mt-1 text-xs text-[var(--text-tertiary)]">
          End of the candidate&apos;s speech to the persona&apos;s first audible word, per turn, as recorded by the realtime service on{" "}
          {bundle.provenance.host_class ?? "this host"}. The product budget is p95 ≤ 1400 ms; a CPU-only laptop does not meet it.
        </p>
        <ol className="mt-3 grid gap-2 sm:grid-cols-2">
          {userTurns.map((t, i) => (
            <li key={t.id} className="flex items-center justify-between rounded-md border px-3 py-2 text-xs">
              <button type="button" onClick={() => waveform.seekToMs(t.start_ms)} className="truncate pr-3 text-left hover:text-[var(--accent)]">
                Answer {i + 1}: “{t.text.slice(0, 48)}…”
              </button>
              <span className="shrink-0 font-mono">
                {bundle.latency_by_turn[t.id]?.e2e !== undefined ? `${bundle.latency_by_turn[t.id]?.e2e} ms` : "not measured"}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <VerdictBlock
        report={bundle.report}
        onSeekMs={waveform.seekToMs}
        turnStartMs={(turnId) => bundle.turns.find((t) => t.id === turnId)?.start_ms ?? null}
      />

      <section ref={scoresRef}>
        <h2 className="text-md font-medium">Scores</h2>
        <div className="mt-3">
          <ScorePanel scores={bundle.scores} turns={bundle.turns} activeCriterion={activeCriterion} onSelectCriterion={setActiveCriterion} />
        </div>
      </section>

      <section>
        <h2 className="text-md font-medium">Delivery</h2>
        <p className="mt-1 text-xs text-[var(--text-tertiary)]">Deterministic, from the transcript and timestamps — not a model judgement.</p>
        <div className="mt-3">
          <DeliveryPanel turns={bundle.turns} sessionDurationMs={bundle.session.duration_ms} />
        </div>
      </section>

      <section>
        <h2 className="text-md font-medium">Transcript</h2>
        <div className="mt-3">
          <Transcript
            turns={bundle.turns}
            sessionId={bundle.session.id}
            onSeekMs={waveform.seekToMs}
            annotatableCriteria={[]}
            personaAudioCache={null}
            personaVoiceId={null}
            readOnly
          />
        </div>
      </section>

      <p className="text-xs text-[var(--text-tertiary)]">
        Scores measure performance against the rubric this scenario&apos;s author wrote. They do not predict hiring outcomes.
      </p>
    </div>
  );
}
