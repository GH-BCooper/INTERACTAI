import { describe, expect, it } from "vitest";
import {
  DOWNSTREAM_SAMPLE_RATE,
  FRAME_KIND_MIC_UP,
  FRAME_KIND_TTS_DOWN,
  HEADER_BYTES,
  PROTOCOL_VERSION,
  UPSTREAM_FRAME_BYTES,
  UPSTREAM_FRAME_SAMPLES,
  UPSTREAM_PAYLOAD_BYTES,
  UPSTREAM_SAMPLE_RATE,
  decodeDownstreamFrame,
  encodeUpstreamFrame,
  floatToInt16Clamped,
} from "./protocol";

describe("frozen protocol constants", () => {
  it("matches the spec exactly", () => {
    expect(PROTOCOL_VERSION).toBe(1);
    expect(FRAME_KIND_MIC_UP).toBe(1);
    expect(FRAME_KIND_TTS_DOWN).toBe(2);
    expect(UPSTREAM_SAMPLE_RATE).toBe(16_000);
    expect(UPSTREAM_FRAME_SAMPLES).toBe(320);
    expect(UPSTREAM_PAYLOAD_BYTES).toBe(640);
    expect(DOWNSTREAM_SAMPLE_RATE).toBe(24_000);
    expect(HEADER_BYTES).toBe(12);
    expect(UPSTREAM_FRAME_BYTES).toBe(652);
  });
});

describe("encodeUpstreamFrame", () => {
  it("produces a 652-byte frame with a big-endian header", () => {
    const payload = new Int16Array(320).fill(1000);
    const buf = encodeUpstreamFrame(42, 1234, payload);
    expect(buf.byteLength).toBe(652);

    const view = new DataView(buf);
    expect(view.getUint8(0)).toBe(1); // version
    expect(view.getUint8(1)).toBe(1); // kind = mic up
    expect(view.getUint16(2)).toBe(0); // reserved
    expect(view.getUint32(4)).toBe(42); // seq
    expect(view.getUint32(8)).toBe(1234); // timestamp_ms

    const payloadOut = new Int16Array(buf, HEADER_BYTES);
    expect(Array.from(payloadOut)).toEqual(Array.from(payload));
  });

  it("rejects a payload of the wrong length", () => {
    expect(() => encodeUpstreamFrame(0, 0, new Int16Array(319))).toThrow();
  });

  it("rejects a negative or overflowing seq", () => {
    const payload = new Int16Array(320);
    expect(() => encodeUpstreamFrame(-1, 0, payload)).toThrow();
    expect(() => encodeUpstreamFrame(2 ** 32, 0, payload)).toThrow();
  });
});

describe("decodeDownstreamFrame", () => {
  it("round-trips an encoded frame", () => {
    const payload = new Int16Array(100);
    for (let i = 0; i < payload.length; i++) payload[i] = i - 50;

    // build a downstream-kind frame by hand (encodeUpstreamFrame is upstream-only)
    const buf = new ArrayBuffer(HEADER_BYTES + payload.byteLength);
    const view = new DataView(buf);
    view.setUint8(0, PROTOCOL_VERSION);
    view.setUint8(1, FRAME_KIND_TTS_DOWN);
    view.setUint32(4, 7);
    view.setUint32(8, 999);
    new Int16Array(buf, HEADER_BYTES).set(payload);

    const decoded = decodeDownstreamFrame(buf);
    expect(decoded.kind).toBe(FRAME_KIND_TTS_DOWN);
    expect(decoded.seq).toBe(7);
    expect(decoded.timestampMs).toBe(999);
    expect(Array.from(decoded.payload)).toEqual(Array.from(payload));
  });

  it("rejects a buffer shorter than the header", () => {
    expect(() => decodeDownstreamFrame(new ArrayBuffer(4))).toThrow();
  });
});

describe("floatToInt16Clamped", () => {
  it("scales in-range values correctly", () => {
    const out = new Int16Array(4);
    floatToInt16Clamped(new Float32Array([0, 1, -1, 0.5]), out);
    // Int16Array assignment truncates toward zero (matches the reference implementation in
    // docs/phase-1-LEARN.md §2 — no rounding), so 0.5 * 0x7fff = 16383.5 truncates to 16383.
    expect(Array.from(out)).toEqual([0, 0x7fff, -0x8000, 16383]);
  });

  it("clamps out-of-range values instead of wrapping", () => {
    const out = new Int16Array(2);
    floatToInt16Clamped(new Float32Array([1.5, -2.3]), out);
    expect(Array.from(out)).toEqual([0x7fff, -0x8000]);
  });
});
