/**
 * Practice room WS lifecycle (Task 3.2) built on top of the frozen protocol in
 * apps/web/lib/ws-types.ts / lib/audio/protocol.ts. Deliberately framework-free — like
 * lib/audio/playback.ts's JitterBuffer/PlaybackQueue, the state machine here is a plain class so
 * it's testable by injecting a fake WebSocket, with a thin `useRealtimeSocket` hook (hooks/) as
 * the only piece that touches React.
 *
 * Reconnection (Task 3.2 edge case: "Network drops for 5s -> connection_trouble, auto-reconnect
 * with resume, no data loss"): a WS token is single-use and short-lived
 * (services/api/app/core/security.py's `mint_ws_token`), so a reconnect can't just re-open the
 * same URL — it must mint a fresh token, then send `resume` (not `hello`) with the last seq
 * numbers seen in each direction so the server's bounded replay buffer
 * (services/realtime/app/main.py::_replay_missed_messages) can fill the gap.
 */
import {
  DOWNSTREAM_SAMPLE_RATE,
  decodeDownstreamFrame,
  FRAME_KIND_TTS_DOWN,
} from "../audio/protocol";
import type { WsMessage } from "../ws-types";

export type ConnectionStatus =
  | "connecting"
  | "open"
  | "reconnecting"
  | "session_busy"
  | "closed"
  | "fatal_error";

export interface RealtimeConnectionHandlers {
  onStatusChange: (status: ConnectionStatus) => void;
  onMessage: (msg: WsMessage) => void;
  onAudioFrame: (payload: Int16Array, sampleRate: number, seq: number) => void;
  /** Must mint a fresh ws token and return its `ws_url` — see services/api's
   * `POST /sessions/{id}/ws-token`. Called on every (re)connect, including the first. */
  mintWsUrl: () => Promise<string>;
}

const PROTOCOL_VERSION = "1.0";
const RECONNECT_BASE_MS = 500;
const RECONNECT_MAX_MS = 5000;
const PING_INTERVAL_MS = 20_000;

/** A structural subset of the real browser `WebSocket` — loose (`any`-typed event params) on
 * purpose so both the real `WebSocket` constructor and a hand-rolled fake in tests satisfy it
 * without fighting TypeScript's function-parameter variance rules over `Event`/`CloseEvent`/
 * `MessageEvent`'s exact shapes, which this module never needs beyond `.code`/`.reason`/`.data`. */
/* eslint-disable @typescript-eslint/no-explicit-any -- deliberately loose: this interface
   exists only so a real `WebSocket` and a hand-rolled test fake both satisfy it without
   TypeScript's function-parameter variance rules fighting over Event/CloseEvent/MessageEvent's
   exact shapes, none of which this module needs beyond `.code`/`.reason`/`.data`. */
export interface WebSocketLike {
  readonly readyState: number;
  binaryType: string;
  onopen: ((ev: any) => void) | null;
  onclose: ((ev: any) => void) | null;
  onerror: ((ev: any) => void) | null;
  onmessage: ((ev: any) => void) | null;
  send(data: string | ArrayBufferLike | ArrayBufferView): void;
  close(code?: number, reason?: string): void;
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export type WebSocketFactory = (url: string) => WebSocketLike;

const CLOSE_CODE_SESSION_BUSY_OR_TOKEN_REUSED = 4409;
const CLOSE_REASON_SESSION_BUSY = "ORCHESTRATION_SESSION_BUSY";

export class RealtimeConnection {
  private ws: WebSocketLike | null = null;
  private status: ConnectionStatus = "connecting";
  private clientSeq = 0;
  private lastServerSeq = -1;
  private lastClientSeq = -1;
  private sessionId: string;
  private clientSampleRate: number;
  private clientFrameMs: number;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private closedByUser = false;
  private hasConnectedOnce = false;

  constructor(
    private readonly handlers: RealtimeConnectionHandlers,
    private readonly wsFactory: WebSocketFactory,
    opts: { sessionId: string; clientSampleRate: number; clientFrameMs: number },
  ) {
    this.sessionId = opts.sessionId;
    this.clientSampleRate = opts.clientSampleRate;
    this.clientFrameMs = opts.clientFrameMs;
  }

  async connect(): Promise<void> {
    this.setStatus(this.hasConnectedOnce ? "reconnecting" : "connecting");
    let url: string;
    try {
      url = await this.handlers.mintWsUrl();
    } catch {
      this.scheduleReconnect();
      return;
    }
    if (this.closedByUser) return;

    const ws = this.wsFactory(url);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => this.handleOpen();
    ws.onclose = (ev) => this.handleClose(ev.code, ev.reason);
    ws.onerror = () => {
      /* onclose always follows onerror for a WS; nothing to do here. */
    };
    ws.onmessage = (ev) => this.handleMessage(ev.data);
    this.ws = ws;
  }

  private handleOpen(): void {
    this.reconnectAttempt = 0;
    const resuming = this.hasConnectedOnce;
    this.hasConnectedOnce = true;
    if (resuming) {
      this.sendText({
        type: "resume",
        seq: this.nextClientSeq(),
        protocol_version: PROTOCOL_VERSION,
        session_id: this.sessionId,
        last_server_seq: this.lastServerSeq,
        last_client_seq: this.lastClientSeq,
      });
    } else {
      this.sendText({
        type: "hello",
        seq: this.nextClientSeq(),
        protocol_version: PROTOCOL_VERSION,
        session_id: this.sessionId,
        client_sample_rate: this.clientSampleRate,
        client_frame_ms: this.clientFrameMs,
        capabilities: [],
      });
    }
    this.setStatus("open");
    this.startPing();
  }

  private handleClose(code: number, reason: string): void {
    this.stopPing();
    this.ws = null;
    if (this.closedByUser) {
      this.setStatus("closed");
      return;
    }
    if (code === CLOSE_CODE_SESSION_BUSY_OR_TOKEN_REUSED && reason === CLOSE_REASON_SESSION_BUSY) {
      this.setStatus("session_busy");
      return;
    }
    if (code === 1000) {
      // Clean server-initiated close (session_closed already delivered the reason to the app).
      this.setStatus("closed");
      return;
    }
    // Anything else — dropped Wi-Fi, a proxy timeout, a crashed server process — is exactly
    // Task 3.2's "connection_trouble, auto-reconnect with resume."
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.closedByUser) return;
    this.setStatus("reconnecting");
    const delay = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * 2 ** this.reconnectAttempt);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => void this.connect(), delay);
  }

  private handleMessage(data: unknown): void {
    if (data instanceof ArrayBuffer) {
      const frame = decodeDownstreamFrame(data);
      if (frame.kind === FRAME_KIND_TTS_DOWN) {
        this.handlers.onAudioFrame(frame.payload, DOWNSTREAM_SAMPLE_RATE, frame.seq);
      }
      return;
    }
    if (typeof data !== "string") return;
    let msg: WsMessage;
    try {
      msg = JSON.parse(data) as WsMessage;
    } catch {
      return;
    }
    if (typeof msg.seq === "number") this.lastServerSeq = Math.max(this.lastServerSeq, msg.seq);
    this.handlers.onMessage(msg);
  }

  private nextClientSeq(): number {
    this.lastClientSeq = this.clientSeq;
    const seq = this.clientSeq;
    this.clientSeq = (this.clientSeq + 1) >>> 0;
    return seq;
  }

  private sendText(payload: Record<string, unknown>): void {
    if (!this.ws || this.ws.readyState !== 1 /* OPEN */) return;
    this.ws.send(JSON.stringify(payload));
  }

  private startPing(): void {
    this.pingTimer = setInterval(() => {
      this.sendText({ type: "ping", seq: this.nextClientSeq(), client_time_ms: Date.now() });
    }, PING_INTERVAL_MS);
  }

  private stopPing(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
  }

  private setStatus(status: ConnectionStatus): void {
    this.status = status;
    this.handlers.onStatusChange(status);
  }

  getStatus(): ConnectionStatus {
    return this.status;
  }

  sendAudioFrame(wireFrame: ArrayBuffer): void {
    if (!this.ws || this.ws.readyState !== 1) return;
    this.ws.send(wireFrame);
  }

  setMuted(muted: boolean): void {
    this.sendText({ type: "mute", seq: this.nextClientSeq(), muted });
  }

  endSession(reason: "user_hangup" | "user_abandoned" = "user_hangup"): void {
    this.sendText({ type: "end_session", seq: this.nextClientSeq(), reason });
  }

  /** Task 3.2: "Closing the tab triggers... a synchronous flush of buffered audio." The server
   * already durably persists audio incrementally during the session (Task 2.2c) — this just
   * asks for a clean close rather than leaving the socket to time out. */
  close(): void {
    this.closedByUser = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.stopPing();
    this.ws?.close(1000, "user_hangup");
  }
}
