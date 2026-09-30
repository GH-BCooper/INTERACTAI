"use client";

import { ClipboardCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { AdminForbidden, AdminPageHeader } from "@/components/admin/admin-chrome";
import { Button } from "@/components/ui/button";
import { Label, Textarea } from "@/components/ui/field";
import { EmptyState, Skeleton } from "@/components/ui/primitives";
import { Switch } from "@/components/ui/switch";
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

  // docs/ui-audit-2026-09.md §12: keyboard-first — 1–5 score the current item, J/K move between
  // items. Ignored while typing in the notes field, so "1" in a note is just a "1".
  const saveRef = useRef(save);
  saveRef.current = save;
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      if (/^[1-5]$/.test(e.key)) {
        e.preventDefault();
        void saveRef.current(Number(e.key));
      } else if (e.key === "j" || e.key === "J") {
        e.preventDefault();
        setIndex((i) => Math.min(i + 1, Math.max(0, items.length - 1)));
      } else if (e.key === "k" || e.key === "K") {
        e.preventDefault();
        setIndex((i) => Math.max(0, i - 1));
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [items.length]);

  if (queueQuery.error instanceof ApiError && queueQuery.error.code === "FORBIDDEN") return <AdminForbidden />;

  const progress = progressQuery.data;
  const roundPct =
    progress && progress.total_candidate_pairs > 0 ? Math.min(100, (progress.labeled_pairs / progress.total_candidate_pairs) * 100) : 0;

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 sm:px-6">
      <AdminPageHeader
        title="Annotate"
        description="Score each answer against the anchor descriptors. Keys: 1–5 to score, J / K for next / previous."
        filters={
          <Switch
            label="Show pre-labels"
            description="Training split only. A suggestion to review, never auto-accepted."
            checked={preLabelledMode}
            onChange={setPreLabelledMode}
          />
        }
      />

      {progress && (
        <div className="mt-4">
          <div className="flex items-center justify-between text-xs text-[var(--text-tertiary)]">
            <span>Round progress</span>
            <span className="font-mono">
              {progress.labeled_pairs} / {progress.total_candidate_pairs}
            </span>
          </div>
          <div
            className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--bg-raised)]"
            role="progressbar"
            aria-label="Labelled pairs this round"
            aria-valuemin={0}
            aria-valuemax={progress.total_candidate_pairs}
            aria-valuenow={progress.labeled_pairs}
          >
            <div className="h-full rounded-full bg-[var(--accent)] transition-[width] duration-150" style={{ width: `${roundPct}%` }} />
          </div>
        </div>
      )}

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
        <Skeleton className="mt-8 h-64 rounded-lg" />
      ) : !current ? (
        <EmptyState
          className="mt-8"
          icon={<ClipboardCheck size={18} />}
          title="Nothing left in your queue"
          body={
            <>
              Either everything has been labelled, or no dataset revision exists yet — run{" "}
              <code className="rounded bg-[var(--bg-raised)] px-1 font-mono">dataset/build.py</code> first.
            </>
          }
        />
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
                aria-keyshortcuts={point}
                className="flex items-start gap-3 rounded-md border px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-[var(--bg-raised)] disabled:opacity-50"
              >
                <kbd className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded border font-mono text-xs">{point}</kbd>
                <span>{current.anchor_descriptors[point] ?? ""}</span>
              </button>
            ))}
          </div>

          <Label htmlFor="notes" className="mt-3">
            Notes (required for extremes — 1 or 5)
          </Label>
          <Textarea
            id="notes"
            value={notes}
            onChange={(e) => {
              setNotes(e.target.value);
              if (e.target.value.trim()) setExtremeNotesError(false);
            }}
            rows={2}
            className="mt-1"
          />
          {extremeNotesError && (
            <p role="alert" className="mt-1 text-xs text-[var(--status-bad)]">
              A note is required for a score of 1 or 5 — justify the extreme before saving.
            </p>
          )}

          {lastSavedRound !== null && (
            <p className="mt-2 text-xs text-[var(--text-tertiary)]">
              Previous item saved (round {lastSavedRound}).
            </p>
          )}

          <div className="mt-4 flex justify-between">
            <Button variant="ghost" size="sm" onClick={() => setIndex((i) => Math.max(0, i - 1))} disabled={index === 0} title="Previous (K)">
              Previous
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIndex((i) => Math.min(i + 1, items.length - 1))}
              disabled={index + 1 >= items.length}
              title="Skip (J)"
            >
              Skip for now
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
