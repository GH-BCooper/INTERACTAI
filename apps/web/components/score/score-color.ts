/**
 * The ONE place any of the four reserved score colour tokens (app/globals.css,
 * CLAUDE.md §1: "RESERVED. These four variables may not be used for anything except rubric
 * values") are referenced by name. Every other component asks this module for a CSS value or a
 * label string instead of writing `var(--score-strong)` etc. itself — apps/web/scripts/
 * check-design-tokens.mjs greps for the literal token names outside this directory, so keeping
 * every other file's source text free of them is what makes that check meaningful rather than
 * a formality.
 */

export type ScoreBand = "strong" | "developing" | "weak" | "insufficient";

const STRONG_THRESHOLD = 4;
const DEVELOPING_THRESHOLD = 2.5;

export function scoreBand(score: number | null): ScoreBand {
  if (score === null) return "insufficient";
  if (score >= STRONG_THRESHOLD) return "strong";
  if (score >= DEVELOPING_THRESHOLD) return "developing";
  return "weak";
}

export function scoreColorVar(score: number | null): string {
  return `var(${scoreBandVarName(scoreBand(score))})`;
}

/** The bare custom-property name (`--score-strong`, not `var(--score-strong)`) — DOM/CSSOM
 * consumers (inline `style`) want the `var()`-wrapped form above; canvas-based consumers (the
 * report waveform, which wavesurfer.js renders to `<canvas>`, outside the CSS cascade — a
 * canvas `fillStyle` never resolves `var()`) need the bare name to look up the computed value
 * themselves via `getComputedStyle` (see lib/theme/resolve-css-var.ts). */
export function scoreBandVarName(band: ScoreBand): string {
  return `--score-${band}`;
}

const BAND_LABEL: Record<ScoreBand, string> = {
  strong: "Strong",
  developing: "Developing",
  weak: "Needs work",
  insufficient: "Not enough signal",
};

/** CLAUDE.md §1.6: "Below the confidence threshold, the UI shows 'not enough signal', never a
 * number." `score === null` is exactly that case — services/coach already gates it server-side,
 * this never re-derives the threshold, only renders what was already decided. */
export function scoreLabel(score: number | null): string {
  return BAND_LABEL[scoreBand(score)];
}
