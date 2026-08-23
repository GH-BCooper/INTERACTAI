import { describe, expect, it } from "vitest";

import { findCurrentTurn, findNearestTurn } from "./derive-current-turn";
import type { TurnOut } from "@/lib/api/types";

function turn(index: number, start_ms: number, end_ms: number): TurnOut {
  return {
    id: `t${index}`,
    index,
    speaker: index % 2 === 0 ? "persona" : "user",
    text: `turn ${index}`,
    text_scrubbed: null,
    start_ms,
    end_ms,
    word_timings: [],
    truncated: false,
    asr_confidence: null,
    metrics: null,
    scores: [],
  };
}

describe("findCurrentTurn", () => {
  const turns = [turn(0, 0, 1000), turn(1, 1000, 3000), turn(2, 3000, 5000)];

  it("finds the turn containing the playhead", () => {
    expect(findCurrentTurn(turns, 1500)?.id).toBe("t1");
  });

  it("start_ms is inclusive, end_ms is exclusive", () => {
    expect(findCurrentTurn(turns, 1000)?.id).toBe("t1");
    expect(findCurrentTurn(turns, 999)?.id).toBe("t0");
  });

  it("returns undefined past the last turn's end", () => {
    expect(findCurrentTurn(turns, 5000)).toBeUndefined();
  });

  it("returns undefined for an empty turn list", () => {
    expect(findCurrentTurn([], 0)).toBeUndefined();
  });
});

describe("findNearestTurn", () => {
  const turns = [turn(0, 100, 1000), turn(1, 1000, 3000)];

  it("matches findCurrentTurn when the playhead is inside a turn", () => {
    expect(findNearestTurn(turns, 500)?.id).toBe("t0");
  });

  it("falls back to the first turn before any turn has started", () => {
    expect(findNearestTurn(turns, 0)?.id).toBe("t0");
  });

  it("falls back to the last turn after the session has ended", () => {
    expect(findNearestTurn(turns, 10_000)?.id).toBe("t1");
  });

  it("returns undefined for an empty turn list", () => {
    expect(findNearestTurn([], 0)).toBeUndefined();
  });
});
