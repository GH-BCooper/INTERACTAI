import { describe, expect, it } from "vitest";
import type {
  AudioChunkMeta,
  Degraded,
  EndSession,
  Hello,
  Interrupted,
  LatencyReport,
  Mute,
  PartialTranscript,
  PersonaText,
  Ping,
  Pong,
  Ready,
  Resume,
  SessionClosed,
  StateChange,
  TurnFinalized,
  WsError,
  WsMessage,
} from "./ws-types";
import { assertNever } from "./ws-assert-never";

const UUID = "11111111-1111-1111-1111-111111111111";

// One literal instance of every WsMessage variant. This is a compile-time check as much as a
// runtime one: if a field is missing or mistyped, `tsc --noEmit` fails before the test runs.
const samples: WsMessage[] = [
  { type: "hello", seq: 1, protocol_version: "1.0", session_id: UUID, client_sample_rate: 16000, client_frame_ms: 20, capabilities: [] } satisfies Hello,
  { type: "resume", seq: 1, protocol_version: "1.0", session_id: UUID, last_server_seq: 0, last_client_seq: 0 } satisfies Resume,
  { type: "mute", seq: 1, muted: true } satisfies Mute,
  { type: "end_session", seq: 1, reason: "user_hangup" } satisfies EndSession,
  { type: "ping", seq: 1, client_time_ms: 0 } satisfies Ping,
  { type: "ready", seq: 1, session_id: UUID, server_sample_rate: 16000, protocol_version: "1.0", resumed: false } satisfies Ready,
  { type: "state_change", seq: 1, state: "listening", client_state: "your_turn", at_ms: 0 } satisfies StateChange,
  { type: "partial_transcript", seq: 1, turn_index: 0, text: "hi", stability: 0.5, at_ms: 0 } satisfies PartialTranscript,
  { type: "turn_finalized", seq: 1, turn_id: UUID, turn_index: 0, text: "hi", start_ms: 0, end_ms: 100, asr_confidence: 0.9, word_timings: [{ word: "hi", start_ms: 0, end_ms: 100 }] } satisfies TurnFinalized,
  { type: "persona_text", seq: 1, turn_id: UUID, text_delta: "hi", done: false } satisfies PersonaText,
  { type: "audio_chunk_meta", seq: 1, turn_id: UUID, chunk_seq: 0, sample_rate: 22050, byte_length: 640, is_final: false } satisfies AudioChunkMeta,
  { type: "interrupted", seq: 1, turn_id: UUID, at_ms: 0, truncated_text: "hi" } satisfies Interrupted,
  { type: "degraded", seq: 1, component: "tts", message: "holding line", recoverable: true } satisfies Degraded,
  { type: "latency_report", seq: 1, turn_id: UUID, stages: [{ stage: "e2e", duration_ms: 1200 }], e2e_ms: 1200 } satisfies LatencyReport,
  { type: "session_closed", seq: 1, reason: "user_hangup", duration_ms: 1000, report_pending: true } satisfies SessionClosed,
  { type: "error", seq: 1, code: "ORCHESTRATION_PROTOCOL_MISMATCH", message: "bad version", recovery: "reconnect", fatal: true, trace_id: "abc" } satisfies WsError,
  { type: "pong", seq: 1, client_time_ms: 0, server_time_ms: 0 } satisfies Pong,
];

describe("WsMessage", () => {
  it("covers every discriminant exactly once", () => {
    const seen = new Set(samples.map((m) => m.type));
    expect(seen.size).toBe(samples.length);
    expect(seen.size).toBe(17);
  });

  it("exhaustively switches over every variant (compile-time exhaustiveness via assertNever)", () => {
    function describeMessage(msg: WsMessage): string {
      switch (msg.type) {
        case "hello": return "hello";
        case "resume": return "resume";
        case "mute": return "mute";
        case "end_session": return "end_session";
        case "ping": return "ping";
        case "ready": return "ready";
        case "state_change": return "state_change";
        case "partial_transcript": return "partial_transcript";
        case "turn_finalized": return "turn_finalized";
        case "persona_text": return "persona_text";
        case "audio_chunk_meta": return "audio_chunk_meta";
        case "interrupted": return "interrupted";
        case "degraded": return "degraded";
        case "latency_report": return "latency_report";
        case "session_closed": return "session_closed";
        case "error": return "error";
        case "pong": return "pong";
        default: return assertNever(msg);
      }
    }

    for (const msg of samples) {
      expect(describeMessage(msg)).toBe(msg.type);
    }
  });
});
