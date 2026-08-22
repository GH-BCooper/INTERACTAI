import { describe, expect, it } from "vitest";

import { AudioTextCorrelator } from "./audio-text-correlator";

describe("AudioTextCorrelator", () => {
  it("completes a chunk once both the frame and the text arrive, in meta/frame/text order", () => {
    const c = new AudioTextCorrelator();
    c.observeMeta("turn-1");
    expect(c.observeFrame(0)).toBeNull();
    const completed = c.observeText("Hello");
    expect(completed).toEqual({ turnId: "turn-1", seq: 0, text: "Hello" });
  });

  it("completes correctly even if the text somehow arrived before the frame", () => {
    const c = new AudioTextCorrelator();
    c.observeMeta("turn-1");
    expect(c.observeText("Hello")).toBeNull();
    expect(c.observeFrame(0)).toEqual({ turnId: "turn-1", seq: 0, text: "Hello" });
  });

  it("handles multiple chunks in sequence without cross-matching", () => {
    const c = new AudioTextCorrelator();
    c.observeMeta("turn-1");
    c.observeFrame(0);
    const first = c.observeText("First chunk.");

    c.observeMeta("turn-1");
    c.observeFrame(1);
    const second = c.observeText("Second chunk.");

    expect(first).toEqual({ turnId: "turn-1", seq: 0, text: "First chunk." });
    expect(second).toEqual({ turnId: "turn-1", seq: 1, text: "Second chunk." });
  });

  it("a stray frame with no matching meta is dropped, not mismatched", () => {
    const c = new AudioTextCorrelator();
    expect(c.observeFrame(99)).toBeNull();
    // A later, legitimate meta must not accidentally pick up seq 99.
    c.observeMeta("turn-1");
    expect(c.observeFrame(1)).toBeNull();
  });

  it("reset() discards any half-matched entry", () => {
    const c = new AudioTextCorrelator();
    c.observeMeta("turn-1");
    c.observeFrame(0);
    c.reset();
    expect(c.observeText("orphaned")).toBeNull();
  });
});
