import type { WordTimingOut } from "@/lib/api/types";

export interface EvidenceSpanLike {
  start: number;
  end: number;
}

export interface TranscriptSegment {
  text: string;
  /** null = not individually clickable — whitespace/punctuation between words, or a word this
   * turn's own ASR word_timings couldn't locate (Task 3.4 edge case: a data bug here degrades
   * to "not clickable", never a crash). */
  startMs: number | null;
  /** Task 3.4d: "evidence spans underlined." */
  underlined: boolean;
}

function overlaps(start: number, end: number, spans: EvidenceSpanLike[]): boolean {
  return spans.some((s) => start < s.end && end > s.start);
}

/** Task 3.4d: "Speaker-labelled, timestamped, evidence spans underlined, click any word to
 * seek." Splits `text` into per-word segments (clickable, timed) interleaved with the
 * whitespace/punctuation between them (not clickable), and marks any segment overlapping an
 * evidence span as underlined — using the same word-location algorithm as
 * lib/report/map-char-offset-to-ms.ts so the two stay consistent with each other. */
export function buildTranscriptSegments(
  text: string,
  wordTimings: WordTimingOut[],
  evidenceSpans: EvidenceSpanLike[],
): TranscriptSegment[] {
  if (wordTimings.length === 0) {
    return [{ text, startMs: null, underlined: evidenceSpans.length > 0 }];
  }

  const segments: TranscriptSegment[] = [];
  let cursor = 0;

  for (const w of wordTimings) {
    const idx = text.indexOf(w.word, cursor);
    if (idx === -1) continue;

    if (idx > cursor) {
      const gap = text.slice(cursor, idx);
      segments.push({ text: gap, startMs: null, underlined: overlaps(cursor, idx, evidenceSpans) });
    }

    const end = idx + w.word.length;
    segments.push({ text: w.word, startMs: w.start_ms, underlined: overlaps(idx, end, evidenceSpans) });
    cursor = end;
  }

  if (cursor < text.length) {
    const tail = text.slice(cursor);
    segments.push({ text: tail, startMs: null, underlined: overlaps(cursor, text.length, evidenceSpans) });
  }

  return segments;
}
