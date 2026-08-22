/**
 * The binary frame format — FROZEN as of Task 1.2d. Mirrors
 * services/realtime/app/audio/protocol.py byte-for-byte; see docs/03-realtime-protocol.md.
 *
 *   offset  size  field
 *   0       1     version        uint8, currently 1
 *   1       1     kind           uint8: 1 = mic PCM up, 2 = TTS audio down
 *   2       2     reserved       uint16, zero
 *   4       4     seq            uint32 big-endian, monotonic per direction
 *   8       4     timestamp_ms   uint32 big-endian, relative to session start
 *   12      n     payload        Int16 PCM little-endian
 */

export const PROTOCOL_VERSION = 1;

export const FRAME_KIND_MIC_UP = 1;
export const FRAME_KIND_TTS_DOWN = 2;

export const UPSTREAM_SAMPLE_RATE = 16_000;
export const UPSTREAM_FRAME_MS = 20;
export const UPSTREAM_FRAME_SAMPLES = 320;
export const UPSTREAM_PAYLOAD_BYTES = UPSTREAM_FRAME_SAMPLES * 2; // 640
export const DOWNSTREAM_SAMPLE_RATE = 24_000;

export const HEADER_BYTES = 12;
export const UPSTREAM_FRAME_BYTES = HEADER_BYTES + UPSTREAM_PAYLOAD_BYTES; // 652

const SEQ_MAX = 0xffffffff;

export interface DecodedFrame {
  version: number;
  kind: number;
  seq: number;
  timestampMs: number;
  payload: Int16Array;
}

/** Builds one upstream wire frame from a resampled, already-clamped Int16 payload. */
export function encodeUpstreamFrame(seq: number, timestampMs: number, payload: Int16Array): ArrayBuffer {
  if (payload.byteLength !== UPSTREAM_PAYLOAD_BYTES) {
    throw new Error(`expected ${UPSTREAM_PAYLOAD_BYTES}-byte payload, got ${payload.byteLength}`);
  }
  if (seq < 0 || seq > SEQ_MAX) throw new Error(`seq out of range: ${seq}`);

  const buf = new ArrayBuffer(UPSTREAM_FRAME_BYTES);
  const view = new DataView(buf);
  view.setUint8(0, PROTOCOL_VERSION);
  view.setUint8(1, FRAME_KIND_MIC_UP);
  view.setUint16(2, 0);
  view.setUint32(4, seq >>> 0);
  view.setUint32(8, timestampMs >>> 0);
  new Int16Array(buf, HEADER_BYTES).set(payload);
  return buf;
}

/** Decodes a downstream TTS audio frame received from the server. */
export function decodeDownstreamFrame(data: ArrayBuffer): DecodedFrame {
  if (data.byteLength < HEADER_BYTES) {
    throw new Error(`frame shorter than header: ${data.byteLength} bytes`);
  }
  const view = new DataView(data);
  const version = view.getUint8(0);
  const kind = view.getUint8(1);
  const seq = view.getUint32(4);
  const timestampMs = view.getUint32(8);
  const payloadBytes = data.byteLength - HEADER_BYTES;
  const payload = new Int16Array(data.slice(HEADER_BYTES, HEADER_BYTES + payloadBytes));
  return { version, kind, seq, timestampMs, payload };
}

/** Float32 [-1,1] -> Int16, with clamping. Unclamped values wrap and produce a loud click. */
export function floatToInt16Clamped(input: Float32Array, out: Int16Array): void {
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]!));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
}
