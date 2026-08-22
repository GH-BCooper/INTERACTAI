import { describe, expect, it } from "vitest";
import { HEADER_BYTES, UPSTREAM_FRAME_SAMPLES } from "./protocol";
import { buildUpstreamWireFrame, type WorkletFrameMessage } from "./capture";

function workletMessage(frameIndex: number, fill: number): WorkletFrameMessage {
  const samples = new Int16Array(UPSTREAM_FRAME_SAMPLES).fill(fill);
  return { type: "frame", frameIndex, buffer: samples.buffer };
}

describe("buildUpstreamWireFrame", () => {
  it("derives the timestamp from frameIndex * 20ms, not wall-clock time", () => {
    const frame = buildUpstreamWireFrame(0, workletMessage(5, 100));
    const view = new DataView(frame);
    expect(view.getUint32(8)).toBe(100); // frameIndex 5 -> 100ms
  });

  it("uses the caller-assigned seq, independent of frameIndex", () => {
    const frame = buildUpstreamWireFrame(999, workletMessage(0, 0));
    const view = new DataView(frame);
    expect(view.getUint32(4)).toBe(999);
  });

  it("preserves payload samples through the header-prepend", () => {
    const frame = buildUpstreamWireFrame(1, workletMessage(1, -12345));
    const payload = new Int16Array(frame, HEADER_BYTES);
    expect(payload.every((s) => s === -12345)).toBe(true);
  });

  it("rejects a worklet message with the wrong sample count", () => {
    const bad: WorkletFrameMessage = { type: "frame", frameIndex: 0, buffer: new Int16Array(100).buffer };
    expect(() => buildUpstreamWireFrame(0, bad)).toThrow();
  });

  it("sequencing is monotonic across successive frames from a stream", () => {
    const seqs = [0, 1, 2, 3].map((frameIndex) =>
      new DataView(buildUpstreamWireFrame(frameIndex, workletMessage(frameIndex, 0))).getUint32(4),
    );
    expect(seqs).toEqual([0, 1, 2, 3]);
  });
});
