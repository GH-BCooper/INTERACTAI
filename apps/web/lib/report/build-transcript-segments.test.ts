import { describe, expect, it } from "vitest";

import { buildTranscriptSegments } from "./build-transcript-segments";

const TEXT = "I rebuilt the pipeline.";
const WORD_TIMINGS = [
  { word: "I", start_ms: 0, end_ms: 100 },
  { word: "rebuilt", start_ms: 100, end_ms: 400 },
  { word: "the", start_ms: 400, end_ms: 500 },
  { word: "pipeline.", start_ms: 500, end_ms: 900 },
];

describe("buildTranscriptSegments", () => {
  it("interleaves clickable word segments with non-clickable gaps, reconstructing the text exactly", () => {
    const segments = buildTranscriptSegments(TEXT, WORD_TIMINGS, []);
    expect(segments.map((s) => s.text).join("")).toBe(TEXT);
    const wordSegments = segments.filter((s) => s.startMs !== null);
    expect(wordSegments.map((s) => s.text)).toEqual(["I", "rebuilt", "the", "pipeline."]);
  });

  it("underlines exactly the segments overlapping an evidence span", () => {
    const rebuiltStart = TEXT.indexOf("rebuilt");
    const theEnd = TEXT.indexOf("the") + "the".length;
    const segments = buildTranscriptSegments(TEXT, WORD_TIMINGS, [
      { start: rebuiltStart, end: theEnd },
    ]);
    const underlinedWords = segments.filter((s) => s.underlined && s.startMs !== null).map((s) => s.text);
    expect(underlinedWords).toEqual(["rebuilt", "the"]);
  });

  it("falls back to one unclickable segment when there are no word timings", () => {
    const segments = buildTranscriptSegments(TEXT, [], []);
    expect(segments).toEqual([{ text: TEXT, startMs: null, underlined: false }]);
  });

  it("marks the whole fallback segment underlined if any evidence span exists at all", () => {
    const segments = buildTranscriptSegments(TEXT, [], [{ start: 0, end: 5 }]);
    expect(segments[0]!.underlined).toBe(true);
  });

  it("skips a word_timing whose word can't be located, without breaking later words", () => {
    const timings = [
      { word: "I", start_ms: 0, end_ms: 100 },
      { word: "NOT_IN_TEXT", start_ms: 100, end_ms: 200 },
      { word: "pipeline.", start_ms: 500, end_ms: 900 },
    ];
    const segments = buildTranscriptSegments(TEXT, timings, []);
    const clickable = segments.filter((s) => s.startMs !== null);
    expect(clickable.map((s) => s.text)).toEqual(["I", "pipeline."]);
  });
});
