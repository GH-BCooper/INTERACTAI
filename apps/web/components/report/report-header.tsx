"use client";

import { Download, Repeat, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

import { StartSessionDialog } from "@/components/dashboard/start-session-dialog";
import { ScoreHero } from "@/components/score/score-hero";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { LocalDate } from "@/components/ui/local-date";
import { capitalize } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api/client";
import { useDeleteRecording, useExportSession } from "@/lib/api/hooks";
import type { ScenarioOut, SessionOut, SessionScoreOut } from "@/lib/api/types";
import { downloadJson } from "@/lib/download";
import { useToastStore } from "@/stores/toast-store";

function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  const totalMinutes = Math.max(1, Math.round(ms / 60_000));
  return `${totalMinutes} min`;
}

/** Task 3.3b. "Practise again", "Export" and "Delete recording" all have real backend support.
 * "Share" is deliberately absent rather than disabled: a signed read-only link is an unanswered
 * design question (docs/ui-audit-2026-09.md §9), and a permanently disabled button is an
 * advertised dead end. */
export function ReportHeader({
  session,
  scenario,
  scores,
  readOnly = false,
}: {
  session: SessionOut;
  scenario: ScenarioOut | undefined;
  scores: SessionScoreOut[];
  /** Phase 6 TASK 6.5: the public /demo renders this same header with no account behind it. */
  readOnly?: boolean;
}) {
  const [showPractiseAgain, setShowPractiseAgain] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const pushToast = useToastStore((s) => s.push);

  const { overall, avgPercentile } = useMemo(() => {
    const rubricScores = scores.filter((s) => s.criterion_key !== "delivery");
    const withScores = rubricScores.filter((s) => s.aggregate_score !== null);
    const overallValue =
      withScores.length > 0
        ? withScores.reduce((sum, s) => sum + (s.aggregate_score ?? 0), 0) / withScores.length
        : null;
    const withPct = rubricScores.filter((s) => s.percentile_vs_self !== null);
    const pct =
      withPct.length > 0 ? withPct.reduce((sum, s) => sum + (s.percentile_vs_self ?? 0), 0) / withPct.length : null;
    return { overall: overallValue, avgPercentile: pct };
  }, [scores]);

  return (
    <div className="flex flex-col gap-5 border-b pb-6 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-lg font-medium">{scenario?.title ?? "Practice session"}</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          {scenario ? `${capitalize(scenario.family)} · ` : ""}
          {session.target_minutes} min target · {formatDuration(session.duration_ms)} actual ·{" "}
          <LocalDate value={session.created_at} />
        </p>
        {avgPercentile !== null && (
          <p className="mt-1 text-xs text-[var(--text-tertiary)]">
            Better than {Math.round(avgPercentile * 100)}% of your own past sessions in this scenario family.
          </p>
        )}
      </div>

      <div className="flex flex-col items-start gap-3 sm:items-end">
        <div className="sm:text-right">
          <span className="text-xs text-[var(--text-tertiary)]">Overall</span>
          <div className="mt-1">
            <ScoreHero score={overall} />
          </div>
        </div>
        {!readOnly && (
          <div className="flex flex-wrap gap-2">
            {scenario && (
              <Button variant="primary" size="sm" onClick={() => setShowPractiseAgain(true)}>
                <Repeat size={14} aria-hidden /> Practise again
              </Button>
            )}
            <ExportButton sessionId={session.id} />
            {session.recording_available && (
              <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)}>
                <Trash2 size={14} aria-hidden /> Delete recording
              </Button>
            )}
          </div>
        )}
      </div>

      {scenario && (
        <StartSessionDialog open={showPractiseAgain} scenario={scenario} onClose={() => setShowPractiseAgain(false)} />
      )}
      {!readOnly && (
        <DeleteRecordingDialog
          open={confirmDelete}
          sessionId={session.id}
          onClose={() => setConfirmDelete(false)}
          onDeleted={() => {
            setConfirmDelete(false);
            pushToast({
              title: "Recording deleted",
              description: "The audio is gone from storage. The transcript and scores are unchanged.",
              variant: "success",
            });
          }}
        />
      )}
    </div>
  );
}

function ExportButton({ sessionId }: { sessionId: string }) {
  const exportSession = useExportSession(sessionId);
  const pushToast = useToastStore((s) => s.push);

  async function run() {
    try {
      const data = await exportSession.mutateAsync();
      downloadJson(`interactai-session-${sessionId.slice(0, 8)}.json`, data);
    } catch (err) {
      pushToast({
        title: "Export failed",
        description: err instanceof ApiError ? err.recovery : "Try again in a moment.",
        variant: "error",
      });
    }
  }

  return (
    <Button variant="secondary" size="sm" onClick={() => void run()} disabled={exportSession.isPending}>
      <Download size={14} aria-hidden /> {exportSession.isPending ? "Exporting…" : "Export"}
    </Button>
  );
}

/** CLAUDE.md §10: "Deletion is genuine, including object storage." A confirmed, irreversible
 * action — so it says exactly what goes and what stays. */
function DeleteRecordingDialog({
  open,
  sessionId,
  onClose,
  onDeleted,
}: {
  open: boolean;
  sessionId: string;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const deleteRecording = useDeleteRecording(sessionId);

  async function confirm() {
    try {
      await deleteRecording.mutateAsync();
      onDeleted();
    } catch {
      // Shown inline below.
    }
  }

  return (
    <Dialog open={open} onClose={onClose} role="alertdialog" labelledBy="delete-recording-title" describedBy="delete-recording-body">
      <h2 id="delete-recording-title" className="text-md font-medium">
        Delete this recording?
      </h2>
      <p id="delete-recording-body" className="mt-2 text-sm text-[var(--text-secondary)]">
        Your audio is permanently removed from storage. The transcript, scores and report stay, but replay will no
        longer play sound. This can&apos;t be undone.
      </p>
      {deleteRecording.error && (
        <p role="alert" className="mt-3 text-xs text-[var(--status-bad)]">
          {deleteRecording.error instanceof ApiError
            ? `${deleteRecording.error.message} ${deleteRecording.error.recovery}`
            : "The recording couldn't be deleted. Try again in a moment."}
        </p>
      )}
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose} data-autofocus>
          Keep it
        </Button>
        <Button variant="danger" size="sm" onClick={() => void confirm()} disabled={deleteRecording.isPending}>
          {deleteRecording.isPending ? "Deleting…" : "Delete recording"}
        </Button>
      </div>
    </Dialog>
  );
}
