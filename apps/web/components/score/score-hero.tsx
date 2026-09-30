import { scoreColorVar, scoreLabel } from "./score-color";

/** The report's hero number: `text-xl` (the token reserved for hero numbers), and — exactly like
 * ScoreBadge — numeral + colour + word, with "not enough signal" in place of a number whenever
 * no criterion had enough signal (CLAUDE.md §1.6). */
export function ScoreHero({ score }: { score: number | null }) {
  return (
    <div className="flex items-center gap-3">
      <span aria-hidden className="h-3 w-3 rounded-full" style={{ backgroundColor: scoreColorVar(score) }} />
      {score === null ? (
        <span className="text-md font-medium text-[var(--text-secondary)]">{scoreLabel(score)}</span>
      ) : (
        <span className="flex items-baseline gap-2">
          <span className="font-mono text-xl">{score.toFixed(1)}</span>
          <span className="text-sm text-[var(--text-tertiary)]">/ 5 · {scoreLabel(score)}</span>
        </span>
      )}
    </div>
  );
}
