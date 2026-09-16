"use client";

import { clsx } from "clsx";
import { Loader2, Repeat, Volume2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { AnnotationControl, type AnnotatableCriterion } from "@/components/report/annotation-control";
import { ScoreBadge } from "@/components/score/score-badge";
import { useRetryQuestion } from "@/lib/api/hooks";
import { buildTranscriptSegments } from "@/lib/report/build-transcript-segments";
import { findCurrentTurn } from "@/lib/report/derive-current-turn";
import type { PersonaAudioCache } from "@/lib/report/persona-audio-cache";
import type { TurnOut } from "@/lib/api/types";
import { usePlayerStore } from "@/stores/player-store";

function formatTimestamp(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

function TranscriptRow({
  turn,
  active,
  onSeekMs,
  sessionId,
  annotatableCriteria,
  personaAudioCache,
  personaVoiceId,
  readOnly,
}: {
  turn: TurnOut;
  active: boolean;
  onSeekMs: (ms: number) => void;
  sessionId: string;
  annotatableCriteria: AnnotatableCriterion[];
  personaAudioCache: PersonaAudioCache | null;
  personaVoiceId: string | null;
  readOnly: boolean;
}) {
  const router = useRouter();
  const retryQuestion = useRetryQuestion(sessionId);
  const [audioState, setAudioState] = useState<"idle" | "loading" | "failed">("idle");

  async function playPersonaTurn() {
    if (!personaAudioCache || !personaVoiceId || !turn.text.trim()) return;
    setAudioState("loading");
    const url = await personaAudioCache.getAudioUrl(turn.id, turn.text, personaVoiceId);
    if (!url) {
      setAudioState("failed");
      return;
    }
    setAudioState("idle");
    void new Audio(url).play();
  }

  async function retryThisQuestion() {
    const retry = await retryQuestion.mutateAsync(turn.id);
    router.push(`/app/practice/${retry.id}`);
  }

  const evidenceSpans = useMemo(
    () => turn.scores.flatMap((s) => s.evidence_spans),
    [turn.scores],
  );
  const segments = useMemo(
    () => buildTranscriptSegments(turn.text, turn.word_timings, evidenceSpans),
    [turn.text, turn.word_timings, evidenceSpans],
  );

  return (
    <div
      className={clsx(
        "rounded-md p-3 transition-colors",
        active ? "bg-[var(--bg-raised)]" : "bg-transparent",
      )}
      style={{ contentVisibility: "auto", containIntrinsicSize: "0 80px" }}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium uppercase tracking-wide text-[var(--text-tertiary)]">
          {turn.speaker === "user" ? "You" : "Persona"}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onSeekMs(turn.start_ms)}
            className="font-mono text-xs text-[var(--text-tertiary)] hover:text-[var(--accent)]"
          >
            {formatTimestamp(turn.start_ms)}
          </button>
          {turn.speaker === "user" && !readOnly && (
            <button
              type="button"
              onClick={() => void retryThisQuestion()}
              disabled={retryQuestion.isPending}
              className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            >
              <Repeat size={12} /> Retry this question
            </button>
          )}
          {turn.speaker === "user" && annotatableCriteria.length > 0 && (
            <AnnotationControl sessionId={sessionId} turnId={turn.id} criteria={annotatableCriteria} />
          )}
          {turn.speaker === "persona" && personaAudioCache && personaVoiceId && (
            <button
              type="button"
              onClick={() => void playPersonaTurn()}
              disabled={audioState === "loading"}
              aria-label="Play this line"
              title={audioState === "failed" ? "Couldn't regenerate audio for this line" : "Play this line"}
              className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            >
              {audioState === "loading" ? (
                <Loader2 size={12} className="animate-thinking" />
              ) : (
                <Volume2 size={12} />
              )}
            </button>
          )}
        </div>
      </div>

      <p className="mt-1.5 text-sm leading-relaxed">
        {segments.map((seg, i) =>
          seg.startMs !== null ? (
            <button
              key={i}
              type="button"
              onClick={() => onSeekMs(seg.startMs!)}
              className={clsx(
                "rounded-sm hover:bg-[var(--bg-raised)]",
                seg.underlined && "underline decoration-[var(--accent)] decoration-2 underline-offset-2",
              )}
            >
              {seg.text}
            </button>
          ) : (
            <span key={i} className={seg.underlined ? "underline decoration-[var(--accent)] decoration-2" : undefined}>
              {seg.text}
            </span>
          ),
        )}
      </p>

      {turn.truncated && (
        <p className="mt-1 text-xs text-[var(--text-tertiary)]">Cut off — session ended mid-answer.</p>
      )}

      {turn.speaker === "user" && turn.scores.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-3">
          {turn.scores
            .filter((s) => s.criterion_key !== "delivery")
            .map((s) => (
              <ScoreBadge key={s.criterion_key} score={s.score} />
            ))}
        </div>
      )}
    </div>
  );
}

/** Task 3.4b/3.4d. Auto-scrolls to the current turn as the playhead moves; a real virtualization
 * library was skipped in favor of `content-visibility: auto` on each row (Task 3.4's "60-turn
 * transcript scrolls at 60fps" — the browser skips layout/paint for off-screen rows without a
 * windowing dependency), which is a lighter-weight technique than list virtualization but not
 * identically verified against a real 60-turn session. */
export function Transcript({
  turns,
  sessionId,
  onSeekMs,
  annotatableCriteria,
  personaAudioCache,
  personaVoiceId,
  readOnly = false,
}: {
  turns: TurnOut[];
  sessionId: string;
  onSeekMs: (ms: number) => void;
  annotatableCriteria: AnnotatableCriterion[];
  personaAudioCache: PersonaAudioCache | null;
  personaVoiceId: string | null;
  /** Phase 6 TASK 6.5: the public /demo has no account, so actions that create sessions hide. */
  readOnly?: boolean;
}) {
  const playheadMs = usePlayerStore((s) => s.playheadMs);
  const currentTurn = useMemo(() => findCurrentTurn(turns, playheadMs), [turns, playheadMs]);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  useEffect(() => {
    if (!currentTurn) return;
    rowRefs.current.get(currentTurn.id)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [currentTurn]);

  return (
    <div className="flex max-h-[32rem] flex-col gap-2 overflow-y-auto pr-1">
      {turns.map((t) => (
        <div key={t.id} ref={(el) => void (el ? rowRefs.current.set(t.id, el) : rowRefs.current.delete(t.id))}>
          <TranscriptRow
            turn={t}
            active={t.id === currentTurn?.id}
            onSeekMs={onSeekMs}
            sessionId={sessionId}
            annotatableCriteria={annotatableCriteria}
            personaAudioCache={personaAudioCache}
            personaVoiceId={personaVoiceId}
            readOnly={readOnly}
          />
        </div>
      ))}
    </div>
  );
}
