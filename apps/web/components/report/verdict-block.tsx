"use client";

import type { ReportOut } from "@/lib/api/types";

/** Task 3.3c. `strengths`/`growth_areas` are the narrator's plain prose (CLAUDE.md §1.4: prose
 * comes from the narrator, already checked server-side against a generic-encouragement
 * blocklist — services/coach/app/narrator — never re-generated or edited here). Only
 * `next_actions` carries a `turn_id` in the schema, so that's the one list rendered as
 * click-to-seek links — the spec's "each linking into the moment that justifies it" is the
 * property `next_actions` was specifically built for (docs/phase-2-BUILD.md TASK 2.5g). */
export function VerdictBlock({ report, onSeekMs, turnStartMs }: {
  report: ReportOut;
  onSeekMs: (ms: number) => void;
  turnStartMs: (turnId: string) => number | null;
}) {
  if (report.status === "pending") {
    return (
      <div className="animate-pulse rounded-lg border bg-[var(--bg-card)] p-4">
        <div className="h-4 w-2/3 rounded bg-[var(--bg-raised)]" />
        <div className="mt-3 h-3 w-full rounded bg-[var(--bg-raised)]" />
        <div className="mt-2 h-3 w-5/6 rounded bg-[var(--bg-raised)]" />
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-[var(--bg-card)] p-4">
      {report.low_sample_size && (
        <p className="mb-3 text-xs text-[var(--text-tertiary)]">
          This session was short — treat these results as a light read, not a full picture.
        </p>
      )}
      {report.summary && <p className="text-sm leading-relaxed">{report.summary}</p>}

      {report.strengths.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium text-[var(--text-tertiary)]">Strengths</p>
          <ul className="mt-1 list-inside list-disc text-sm">
            {report.strengths.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      {report.growth_areas.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium text-[var(--text-tertiary)]">Room to improve</p>
          <ul className="mt-1 list-inside list-disc text-sm">
            {report.growth_areas.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      {report.next_actions.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium text-[var(--text-tertiary)]">Try next</p>
          <ul className="mt-1 flex flex-col gap-1.5">
            {report.next_actions.map((a, i) => {
              const ms = a.turn_id ? turnStartMs(a.turn_id) : null;
              return (
                <li key={i} className="text-sm">
                  {ms !== null ? (
                    <button
                      type="button"
                      onClick={() => onSeekMs(ms)}
                      className="text-left underline decoration-[var(--accent)] decoration-2 underline-offset-2 hover:text-[var(--accent)]"
                    >
                      {a.text}
                    </button>
                  ) : (
                    a.text
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
