import type { TurnOut } from "@/lib/api/types";

/** Task 3.4a's exact derivation: `turns.find(t => playheadMs >= t.start_ms && playheadMs <
 * t.end_ms)`. Pulled out as a standalone function so it's testable without mounting the
 * waveform or the store, and so every consumer (transcript scroll, score panel, turn detail)
 * computes the same answer the same way. */
export function findCurrentTurn(turns: TurnOut[], playheadMs: number): TurnOut | undefined {
  return turns.find((t) => playheadMs >= t.start_ms && playheadMs < t.end_ms);
}

/** A playhead sitting exactly at (or past) the final turn's end, or before any turn starts,
 * still needs a sane "nearest" answer for e.g. highlighting — used by the transcript's
 * auto-scroll so the last line doesn't lose its highlight the instant playback ends. */
export function findNearestTurn(turns: TurnOut[], playheadMs: number): TurnOut | undefined {
  const exact = findCurrentTurn(turns, playheadMs);
  if (exact) return exact;
  if (turns.length === 0) return undefined;
  if (playheadMs < turns[0]!.start_ms) return turns[0];
  return turns[turns.length - 1];
}
