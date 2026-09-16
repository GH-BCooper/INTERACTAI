"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import {
  useAdminAnnotationProgress,
  useAdminAnnotationQueue,
  useAdminAnnotationSubmit,
} from "@/lib/api/hooks";

const SCALE_POINTS = ["1", "2", "3", "4", "5"] as const;

/**
 * docs/phase-5-BUILD.md TASK 5.3a — the admin-only annotation tool. Shows the question, the
 * (PII-scrubbed-if-available) answer text, the audio, the criterion, and the full anchor
 * descriptors for all five points. Never shows a model prediction — the only score-shaped field
 * this page ever receives is `pre_label_score`, and even that only appears for train-split
 * items, requires an explicit score submission either way (no "accept" action exists anywhere
 * on this page), and is visually distinguished as a suggestion, not a fact.
 */
export default function AnnotatePage() {
  const [preLabelledMode, setPreLabelledMode] = useState(false);
  const queueQuery = useAdminAnnotationQueue({ limit: 10, preLabelled: preLabelledMode });
  const progressQuery = useAdminAnnotationProgress();
  const submit = useAdminAnnotationSubmit();

  const [index, setIndex] = useState(0);
  const [notes, setNotes] = useState("");
  const [lastSavedRound, setLastSavedRound] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  const items = queueQuery.data ?? [];
  const current = items[index];

  useEffect(() => {
    setIndex(0);
    setNotes("");
    setLastSavedRound(null);
  }, [queueQuery.dataUpdatedAt]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !current?.audio_url) return;
    function onLoaded() {
      el!.currentTime = current!.audio_start_ms / 1000;
    }
    function onTimeUpdate() {
      if (el!.currentTime * 1000 >= current!.audio_end_ms) {
        el!.pause();
      }
    }
    el.addEventListener("loadedmetadata", onLoaded);
    el.addEventListener("timeupdate", onTimeUpdate);
    return () => {
      el.removeEventListener("loadedmetadata", onLoaded);
      el.removeEventListener("timeupdate", onTimeUpdate);
    };
  }, [current]);

  const [extremeNotesError, setExtremeNotesError] = useState(false);

  async function save(score: number) {
    if (!current) return;
    // Task 5.3a: "a notes field (required for extremes)."
    if ((score === 1 || score === 5) && !notes.trim()) {
      setExtremeNotesError(true);
      return;
    }
    setExtremeNotesError(false);
    const result = await submit.mutateAsync({
      turn_id: current.turn_id,
      criterion_key: current.criterion_key,
      score,
      notes: notes || null,
      pre_label_score: current.pre_label_score,
    });
    setLastSavedRound(result.round);
    setNotes("");
    if (index + 1 < items.length) {
      setIndex(index + 1);
    } else {
      queueQuery.refetch();
    }
  }

  if (queueQuery.error instanceof ApiError && queueQuery.error.code === "FORBIDDEN") {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <h1 className="text-lg font-medium">Admin access required</h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">
          This tool is restricted to admin accounts (docs/decisions/0019).
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-medium">Annotate</h1>
        <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={preLabelledMode}
            onChange={(e) => setPreLabelledMode(e.target.checked)}
          />
          Show pre-labels (training split only)
        </label>
      </div>

      {progressQuery.data && (
        <div className="mt-3 grid grid-cols-2 gap-3 rounded-lg border bg-[var(--bg-card)] p-3 text-xs sm:grid-cols-4">
          <div>
            <p className="text-[var(--text-tertiary)]">Labelled pairs</p>
            <p className="font-mono">{progressQuery.data.labeled_pairs}</p>
          </div>
          <div>
            <p className="text-[var(--text-tertiary)]">Candidate pairs</p>
            <p className="font-mono">{progressQuery.data.total_candidate_pairs}</p>
          </div>
          <div>
            <p className="text-[var(--text-tertiary)]">Double-labelled (2 annotators)</p>
            <p className="font-mono">
              {progressQuery.data.double_labeled_with_two_annotators} / {progressQuery.data.double_labeled_target}
            </p>
          </div>
          <div>
            <p className="text-[var(--text-tertiary)]">Pending adjudication</p>
            <p className="font-mono">{progressQuery.data.disagreements_pending_adjudication}</p>
          </div>
        </div>
      )}

      {queueQuery.isPending ? (
        <div className="mt-8 h-64 animate-pulse rounded-lg border bg-[var(--bg-card)]" />
      ) : !current ? (
        <div className="mt-8 rounded-lg border bg-[var(--bg-card)] px-6 py-16 text-center text-sm text-[var(--text-secondary)]">
          Nothing left in your queue right now. Either everything has been labelled, or no
          dataset revision exists yet — run{" "}
          <code className="rounded bg-[var(--bg-raised)] px-1">dataset/build.py</code> first.
        </div>
      ) : (
        <div className="mt-6 rounded-lg border bg-[var(--bg-card)] p-5">
          <div className="flex items-center justify-between text-xs text-[var(--text-tertiary)]">
            <span>
              {index + 1} / {items.length} in this batch — split: {current.split}
              {current.double_labeled && " — double-labelled subset"}
            </span>
          </div>

          <p className="mt-3 text-sm text-[var(--text-secondary)]">Question</p>
          <p className="text-sm">{current.question || "(no preceding question found)"}</p>

          <p className="mt-4 text-sm text-[var(--text-secondary)]">
            Answer {current.answer_is_scrubbed ? "(PII-scrubbed)" : "(unscrubbed — no report generated yet)"}
          </p>
          <p className="whitespace-pre-wrap text-sm">{current.answer_text}</p>

          {current.audio_url ? (
            <audio ref={audioRef} controls src={current.audio_url} className="mt-3 w-full" />
          ) : (
            <p className="mt-3 text-xs text-[var(--text-tertiary)]">
              No audio available for this turn.
            </p>
          )}

          {current.pre_label_score !== null && (
            <div className="mt-4 rounded-md border border-dashed px-3 py-2 text-xs text-[var(--text-secondary)]">
              AI suggestion (training split only, review and correct — never auto-accepted):{" "}
              <strong>{current.pre_label_score}</strong>
            </div>
          )}

          <p className="mt-4 text-sm font-medium">
            {current.criterion_name}{" "}
            <span className="font-normal text-[var(--text-tertiary)]">({current.criterion_key})</span>
          </p>
          <div className="mt-2 flex flex-col gap-1.5">
            {SCALE_POINTS.map((point) => (
              <button
                key={point}
                type="button"
                onClick={() => void save(Number(point))}
                disabled={submit.isPending}
                className="rounded-md border px-3 py-2 text-left text-sm hover:bg-[var(--bg-raised)]"
              >
                <span className="font-mono font-medium">{point}</span> —{" "}
                {current.anchor_descriptors[point] ?? ""}
              </button>
            ))}
          </div>

          <label className="mt-3 block text-xs text-[var(--text-secondary)]" htmlFor="notes">
            Notes (required for extremes — 1 or 5)
          </label>
          <textarea
            id="notes"
            value={notes}
            onChange={(e) => {
              setNotes(e.target.value);
              if (e.target.value.trim()) setExtremeNotesError(false);
            }}
            rows={2}
            className="mt-1 w-full rounded-md border bg-[var(--bg-page)] px-2 py-1.5 text-xs"
          />
          {extremeNotesError && (
            <p className="mt-1 text-xs text-[var(--danger)]">
              A note is required for a score of 1 or 5 — justify the extreme before saving.
            </p>
          )}

          {lastSavedRound !== null && (
            <p className="mt-2 text-xs text-[var(--text-tertiary)]">
              Previous item saved (round {lastSavedRound}).
            </p>
          )}

          <div className="mt-4 flex justify-end">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIndex((i) => Math.min(i + 1, items.length - 1))}
              disabled={index + 1 >= items.length}
            >
              Skip for now
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
