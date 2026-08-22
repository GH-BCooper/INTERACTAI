"use client";

import { Tag } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { useAnnotate } from "@/lib/api/hooks";

export interface AnnotatableCriterion {
  key: string;
  name: string;
  anchor_descriptors: Record<string, string>;
}

const SCALE_POINTS = ["1", "2", "3", "4", "5"] as const;

/**
 * Task 3.4e (CS-15): "A discreet per-turn control to record a human score against any
 * criterion... This is how the training set grows without a separate tool." The model's own
 * prediction for this turn is never passed into this component at all — not hidden via CSS, not
 * fetched and withheld, simply never in scope here — so there is no way for it to leak into the
 * label even by accident.
 */
export function AnnotationControl({
  sessionId,
  turnId,
  criteria,
}: {
  sessionId: string;
  turnId: string;
  criteria: AnnotatableCriterion[];
}) {
  const [open, setOpen] = useState(false);
  const [criterionKey, setCriterionKey] = useState(criteria[0]?.key ?? "");
  const [notes, setNotes] = useState("");
  const [savedRound, setSavedRound] = useState<number | null>(null);
  const annotate = useAnnotate(sessionId);

  const criterion = criteria.find((c) => c.key === criterionKey);

  async function save(score: number) {
    const result = await annotate.mutateAsync({ turn_id: turnId, criterion_key: criterionKey, score, notes: notes || null });
    setSavedRound(result.round);
  }

  if (criteria.length === 0) return null;

  return (
    <div className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="Rate this answer"
        className="flex items-center gap-1 rounded-md border px-2 py-1 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
      >
        <Tag size={12} /> Rate
      </button>

      {open && (
        <div className="absolute left-0 top-8 z-30 w-72 rounded-lg border bg-[var(--bg-card)] p-4 text-sm shadow-none">
          <p className="font-medium">Record a human score</p>

          <label className="mt-3 block text-xs text-[var(--text-secondary)]" htmlFor={`criterion-${turnId}`}>
            Criterion
          </label>
          <select
            id={`criterion-${turnId}`}
            value={criterionKey}
            onChange={(e) => {
              setCriterionKey(e.target.value);
              setSavedRound(null);
            }}
            className="mt-1 w-full rounded-md border bg-[var(--bg-page)] px-2 py-1.5 text-xs"
          >
            {criteria.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
          </select>

          <div className="mt-3 flex flex-col gap-1.5">
            {SCALE_POINTS.map((point) => (
              <button
                key={point}
                type="button"
                onClick={() => void save(Number(point))}
                disabled={annotate.isPending}
                className="rounded-md border px-2 py-1.5 text-left text-xs hover:bg-[var(--bg-raised)]"
              >
                <span className="font-mono font-medium">{point}</span> — {criterion?.anchor_descriptors[point] ?? ""}
              </button>
            ))}
          </div>

          <label className="mt-3 block text-xs text-[var(--text-secondary)]" htmlFor={`notes-${turnId}`}>
            Notes (optional)
          </label>
          <textarea
            id={`notes-${turnId}`}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="mt-1 w-full rounded-md border bg-[var(--bg-page)] px-2 py-1.5 text-xs"
          />

          {savedRound !== null && (
            <p className="mt-2 text-xs text-[var(--text-tertiary)]">Saved (round {savedRound}).</p>
          )}

          <div className="mt-3 flex justify-end">
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
              Close
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
