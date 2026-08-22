import { describe, expect, it } from "vitest";

import { scoreBand, scoreColorVar, scoreLabel } from "./score-color";

describe("scoreBand", () => {
  it("null is always insufficient, regardless of any numeric convention", () => {
    expect(scoreBand(null)).toBe("insufficient");
    expect(scoreLabel(null)).toBe("Not enough signal");
  });

  it("bands a 1-5 scale into strong/developing/weak at the documented thresholds", () => {
    expect(scoreBand(5)).toBe("strong");
    expect(scoreBand(4)).toBe("strong");
    expect(scoreBand(3.9)).toBe("developing");
    expect(scoreBand(2.5)).toBe("developing");
    expect(scoreBand(2.4)).toBe("weak");
    expect(scoreBand(1)).toBe("weak");
  });

  it("scoreColorVar always references one of the four reserved tokens", () => {
    expect(scoreColorVar(5)).toBe("var(--score-strong)");
    expect(scoreColorVar(3)).toBe("var(--score-developing)");
    expect(scoreColorVar(1)).toBe("var(--score-weak)");
    expect(scoreColorVar(null)).toBe("var(--score-insufficient)");
  });
});
