import { describe, expect, it } from "vitest";

import { mapCharOffsetToMs } from "./map-char-offset-to-ms";

const TEXT = "I rebuilt the ingestion pipeline using the old Kafka setup.";
const WORD_TIMINGS = [
  { word: "I", start_ms: 0, end_ms: 100 },
  { word: "rebuilt", start_ms: 100, end_ms: 400 },
  { word: "the", start_ms: 400, end_ms: 500 },
  { word: "ingestion", start_ms: 500, end_ms: 900 },
  { word: "pipeline", start_ms: 900, end_ms: 1300 },
  { word: "using", start_ms: 1300, end_ms: 1500 },
  { word: "the", start_ms: 1500, end_ms: 1600 },
  { word: "old", start_ms: 1600, end_ms: 1800 },
  { word: "Kafka", start_ms: 1800, end_ms: 2100 },
  { word: "setup.", start_ms: 2100, end_ms: 2500 },
];

describe("mapCharOffsetToMs", () => {
  it("maps an offset inside the first word", () => {
    expect(mapCharOffsetToMs(TEXT, WORD_TIMINGS, 0)).toBe(0);
  });

  it("maps an offset inside a later word", () => {
    const idx = TEXT.indexOf("Kafka");
    expect(mapCharOffsetToMs(TEXT, WORD_TIMINGS, idx)).toBe(1800);
  });

  it("resolves a repeated word to its correct, later occurrence", () => {
    // The second "the" starts after "pipeline using " — must not match the first "the".
    const secondThe = TEXT.indexOf("the", TEXT.indexOf("ingestion"));
    expect(mapCharOffsetToMs(TEXT, WORD_TIMINGS, secondThe)).toBe(1500);
  });

  it("returns null for an out-of-range offset rather than throwing", () => {
    expect(mapCharOffsetToMs(TEXT, WORD_TIMINGS, -1)).toBeNull();
    expect(mapCharOffsetToMs(TEXT, WORD_TIMINGS, TEXT.length + 50)).toBeNull();
  });

  it("returns null when there are no word timings at all", () => {
    expect(mapCharOffsetToMs(TEXT, [], 5)).toBeNull();
  });

  it("returns null for an offset that falls in a gap no word timing covers", () => {
    // A single-word "text" with a timing that doesn't actually appear in it.
    expect(mapCharOffsetToMs("hello world", [{ word: "goodbye", start_ms: 0, end_ms: 100 }], 3)).toBeNull();
  });
});
