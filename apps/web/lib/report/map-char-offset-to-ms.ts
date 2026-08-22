import type { WordTimingOut } from "@/lib/api/types";

/**
 * Task 3.4c: "Click any evidence span -> seek audio to that moment." Evidence spans are char
 * offsets into `turns.text` (CLAUDE.md §1.5, verified server-side by exact substring match) —
 * to turn one into a seek time, walk `word_timings` and locate each word's own substring within
 * `text` (searching forward from the end of the previous match, so a repeated word like "the"
 * is matched to its correct occurrence, not always the first). Returns `null` — never throws,
 * never guesses — when the offset can't be confidently placed, matching the report's own edge
 * case: "Evidence span offsets out of range (data bug) -> span not rendered; logged; score
 * still shown."
 */
export function mapCharOffsetToMs(
  text: string,
  wordTimings: WordTimingOut[],
  charOffset: number,
): number | null {
  if (charOffset < 0 || charOffset > text.length || wordTimings.length === 0) return null;

  let cursor = 0;
  for (const w of wordTimings) {
    const idx = text.indexOf(w.word, cursor);
    if (idx === -1) continue;
    const end = idx + w.word.length;
    if (charOffset >= idx && charOffset <= end) return w.start_ms;
    cursor = end;
  }
  return null;
}
