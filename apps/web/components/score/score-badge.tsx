import { scoreColorVar, scoreLabel } from "./score-color";

/** Task 3.3d/CLAUDE.md §1.6: every score is a numeral, a colour, AND a textual label — never
 * colour alone (accessibility, and "not enough signal" must never look like a greyed-out
 * number that could be misread as zero). */
export function ScoreBadge({ score }: { score: number | null }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-sm">
      <span
        aria-hidden
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: scoreColorVar(score) }}
      />
      <span>{score === null ? "—" : score.toFixed(1)}</span>
      <span className="text-xs font-sans text-[var(--text-tertiary)]">{scoreLabel(score)}</span>
    </span>
  );
}
