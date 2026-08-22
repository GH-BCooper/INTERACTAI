"use client";

import { clsx } from "clsx";
import { useState } from "react";

import { ScoreBadge } from "@/components/score/score-badge";
import type { SessionScoreOut, TurnOut } from "@/lib/api/types";

function ScoreRow({
  score,
  turns,
  active,
  onSelect,
}: {
  score: SessionScoreOut;
  turns: TurnOut[];
  active: boolean;
  onSelect: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const achievedAnchor =
    score.aggregate_score !== null
      ? score.anchor_descriptors[String(Math.round(score.aggregate_score))]
      : null;
  const contributingTurns = turns.filter((t) => score.evidence_turn_ids.includes(t.id));

  return (
    <div className={clsx("rounded-md p-3 transition-colors", active && "bg-[var(--bg-raised)]")}>
      <button type="button" onClick={onSelect} className="flex w-full items-center justify-between text-left">
        <span className="text-sm font-medium">{score.name}</span>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[var(--text-tertiary)]">
            {Math.round(score.confidence * 100)}% confidence
          </span>
          <ScoreBadge score={score.aggregate_score} />
        </div>
      </button>

      {score.percentile_vs_self !== null && (
        <div className="mt-2" title="Compared with your own past sessions in this scenario family">
          <div className="h-1 w-full rounded-full bg-[var(--bg-page)]">
            <div
              className="h-full rounded-full bg-[var(--accent)]"
              style={{ width: `${Math.round(score.percentile_vs_self * 100)}%` }}
            />
          </div>
        </div>
      )}

      {achievedAnchor && (
        <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{achievedAnchor}</p>
      )}

      {contributingTurns.length > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="mt-2 text-xs text-[var(--accent)] hover:text-[var(--accent-hover)]"
        >
          {expanded ? "Hide" : "Show"} {contributingTurns.length} contributing turn
          {contributingTurns.length === 1 ? "" : "s"}
        </button>
      )}
      {expanded && (
        <ul className="mt-2 flex flex-col gap-1.5 border-l pl-3">
          {contributingTurns.map((t) => (
            <li key={t.id} className="text-xs text-[var(--text-secondary)]">
              {t.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Task 3.3d: one row per criterion — score, confidence, a percentile bar against the user's own
 * history, the rubric's own anchor text for the achieved value, and an expander for the turns
 * that justified it. "not enough signal" (aggregate_score === null) renders via ScoreBadge the
 * same way a real score does — same layout, no special-cased empty space (Task 3.4's own edge
 * case: "Turn has no scores -> panel shows 'not enough signal', not empty space"). */
export function ScorePanel({
  scores,
  turns,
  activeCriterion,
  onSelectCriterion,
}: {
  scores: SessionScoreOut[];
  turns: TurnOut[];
  activeCriterion: string | null;
  onSelectCriterion: (key: string) => void;
}) {
  const rubricScores = scores.filter((s) => s.criterion_key !== "delivery");

  if (rubricScores.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-4 text-center text-xs text-[var(--text-tertiary)]">
        Scoring hasn&apos;t started yet.
      </div>
    );
  }

  return (
    <div className="flex flex-col divide-y" style={{ borderColor: "var(--border-subtle)" }}>
      {rubricScores.map((s) => (
        <ScoreRow
          key={s.criterion_key}
          score={s}
          turns={turns}
          active={activeCriterion === s.criterion_key}
          onSelect={() => onSelectCriterion(s.criterion_key)}
        />
      ))}
    </div>
  );
}
