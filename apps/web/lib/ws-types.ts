/* eslint-disable */
/**
 * GENERATED — DO NOT EDIT. Run `make schema`.
 *
 * Source: packages/schema/ws-messages.schema.json
 * Generator: packages/schema/generate.ts -> json-schema-to-typescript
 */


/**
 * Monotonic uint32, per direction (client and server each keep their own counter).
 *
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "seq".
 */
export type Seq = number;
/**
 * The 10 realtime turn/connection states (protocol_version 1.1). See docs/decisions/0001-realtime-state-machine.md and docs/decisions/0008-phase-2-state-machine.md.
 *
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "server_machine_state".
 */
export type ServerMachineState =
  | "connecting"
  | "idle"
  | "listening"
  | "endpointing"
  | "thinking"
  | "speaking"
  | "interrupted"
  | "closing"
  | "degraded"
  | "closed";
/**
 * The 5 user-visible states the practice-room UI renders (protocol_version 1.1). Collapses server_machine_state — see docs/decisions/0008-phase-2-state-machine.md.
 *
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "client_state".
 */
export type ClientState = "your_turn" | "thinking" | "speaking" | "connection_trouble" | "ended";

/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "word_timing".
 */
export interface WordTiming {
  word: string;
  start_ms: number;
  end_ms: number;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "latency_stage".
 */
export interface LatencyStage {
  /**
   * Fixed enum — CLAUDE.md §8.
   */
  stage:
    | "endpoint_detect"
    | "asr_finalize"
    | "prompt_assemble"
    | "model_ttft"
    | "first_chunk_assemble"
    | "tts_first_chunk"
    | "transport"
    | "e2e";
  duration_ms: number;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "hello".
 */
export interface Hello {
  type: "hello";
  seq: Seq;
  /**
   * e.g. "1.0". Mismatched major version -> error ORCHESTRATION_PROTOCOL_MISMATCH, fatal.
   */
  protocol_version: string;
  session_id: string;
  client_sample_rate: number;
  client_frame_ms: number;
  capabilities: string[];
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "resume".
 */
export interface Resume {
  type: "resume";
  seq: Seq;
  protocol_version: string;
  session_id: string;
  last_server_seq: Seq;
  last_client_seq: Seq;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "mute".
 */
export interface Mute {
  type: "mute";
  seq: Seq;
  muted: boolean;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "end_session".
 */
export interface EndSession {
  type: "end_session";
  seq: Seq;
  reason: "user_hangup" | "user_abandoned";
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "ping".
 */
export interface Ping {
  type: "ping";
  seq: Seq;
  client_time_ms: number;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "ready".
 */
export interface Ready {
  type: "ready";
  seq: Seq;
  session_id: string;
  server_sample_rate: number;
  protocol_version: string;
  resumed: boolean;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "state_change".
 */
export interface StateChange {
  type: "state_change";
  seq: Seq;
  state: ServerMachineState;
  client_state: ClientState;
  at_ms: number;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "partial_transcript".
 */
export interface PartialTranscript {
  type: "partial_transcript";
  seq: Seq;
  turn_index: number;
  text: string;
  stability: number;
  at_ms: number;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "turn_finalized".
 */
export interface TurnFinalized {
  type: "turn_finalized";
  seq: Seq;
  turn_id: string;
  turn_index: number;
  text: string;
  start_ms: number;
  end_ms: number;
  asr_confidence: number;
  word_timings: WordTiming[];
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "persona_text".
 */
export interface PersonaText {
  type: "persona_text";
  seq: Seq;
  turn_id: string;
  text_delta: string;
  done: boolean;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "audio_chunk_meta".
 */
export interface AudioChunkMeta {
  type: "audio_chunk_meta";
  seq: Seq;
  turn_id: string;
  chunk_seq: number;
  sample_rate: number;
  byte_length: number;
  is_final: boolean;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "interrupted".
 */
export interface Interrupted {
  type: "interrupted";
  seq: Seq;
  turn_id: string;
  at_ms: number;
  truncated_text: string;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "degraded".
 */
export interface Degraded {
  type: "degraded";
  seq: Seq;
  component: "asr" | "tts" | "persona" | "transport";
  message: string;
  recoverable: boolean;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "latency_report".
 */
export interface LatencyReport {
  type: "latency_report";
  seq: Seq;
  turn_id: string;
  stages: LatencyStage[];
  e2e_ms: number;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "session_closed".
 */
export interface SessionClosed {
  type: "session_closed";
  seq: Seq;
  reason: string;
  duration_ms: number;
  report_pending: boolean;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "error".
 */
export interface WsError {
  type: "error";
  seq: Seq;
  code: string;
  message: string;
  recovery: string;
  fatal: boolean;
  trace_id: string;
}
/**
 * This interface was referenced by `WsDefs`'s JSON-Schema
 * via the `definition` "pong".
 */
export interface Pong {
  type: "pong";
  seq: Seq;
  client_time_ms: number;
  server_time_ms: number;
}

export type WsMessage = Hello | Resume | Mute | EndSession | Ping | Ready | StateChange | PartialTranscript | TurnFinalized | PersonaText | AudioChunkMeta | Interrupted | Degraded | LatencyReport | SessionClosed | WsError | Pong;
