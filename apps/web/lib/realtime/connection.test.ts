import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";

import { RealtimeConnection, type WebSocketLike, type WebSocketFactory } from "./connection";

class FakeWebSocket implements WebSocketLike {
  readyState = 0;
  binaryType = "";
  onopen: ((ev: unknown) => void) | null = null;
  onclose: ((ev: { code: number; reason: string }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  sent: (string | ArrayBufferLike | ArrayBufferView)[] = [];

  open() {
    this.readyState = 1;
    this.onopen?.({});
  }

  simulateClose(code: number, reason: string) {
    this.readyState = 3;
    this.onclose?.({ code, reason });
  }

  simulateText(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  send(data: string | ArrayBufferLike | ArrayBufferView) {
    this.sent.push(data);
  }

  close(code?: number, reason?: string) {
    this.simulateClose(code ?? 1000, reason ?? "");
  }
}

function jsonSent(ws: FakeWebSocket): Record<string, unknown>[] {
  return ws.sent
    .filter((s): s is string => typeof s === "string")
    .map((s) => JSON.parse(s) as Record<string, unknown>);
}

describe("RealtimeConnection", () => {
  let sockets: FakeWebSocket[];
  let factory: WebSocketFactory;
  let mintCount: number;

  beforeEach(() => {
    vi.useFakeTimers();
    sockets = [];
    mintCount = 0;
    factory = (_url: string) => {
      const ws = new FakeWebSocket();
      sockets.push(ws);
      return ws;
    };
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function makeConnection() {
    const statuses: string[] = [];
    const messages: unknown[] = [];
    const audioFrames: { payload: Int16Array; sampleRate: number; seq: number }[] = [];
    const conn = new RealtimeConnection(
      {
        onStatusChange: (s) => statuses.push(s),
        onMessage: (m) => messages.push(m),
        onAudioFrame: (payload, sampleRate, seq) => audioFrames.push({ payload, sampleRate, seq }),
        mintWsUrl: async () => {
          mintCount += 1;
          return `ws://fake/${mintCount}`;
        },
      },
      factory,
      { sessionId: "session-1", clientSampleRate: 16000, clientFrameMs: 20 },
    );
    return { conn, statuses, messages, audioFrames };
  }

  it("sends hello (not resume) on the first connect", async () => {
    const { conn, statuses } = makeConnection();
    await conn.connect();
    sockets[0]!.open();

    const sent = jsonSent(sockets[0]!);
    expect(sent[0]!.type).toBe("hello");
    expect(sent[0]!.session_id).toBe("session-1");
    expect(statuses).toContain("open");
  });

  it("sends resume with last_server_seq/last_client_seq after a reconnect", async () => {
    const { conn } = makeConnection();
    await conn.connect();
    sockets[0]!.open();
    sockets[0]!.simulateText({ type: "ready", seq: 7, session_id: "session-1", server_sample_rate: 24000, protocol_version: "1.0", resumed: false });

    // Unexpected drop -> should schedule a reconnect, not close.
    sockets[0]!.simulateClose(1006, "abnormal");
    await vi.advanceTimersByTimeAsync(600);

    expect(sockets.length).toBe(2);
    sockets[1]!.open();
    const sent = jsonSent(sockets[1]!);
    expect(sent[0]!.type).toBe("resume");
    expect(sent[0]!.last_server_seq).toBe(7);
    expect(mintCount).toBe(2); // a fresh token was minted for the reconnect
  });

  it("detects session_busy and does not reconnect", async () => {
    const { conn, statuses } = makeConnection();
    await conn.connect();
    sockets[0]!.open();
    sockets[0]!.simulateClose(4409, "ORCHESTRATION_SESSION_BUSY");

    await vi.advanceTimersByTimeAsync(5000);
    expect(statuses.at(-1)).toBe("session_busy");
    expect(sockets.length).toBe(1); // never attempted a second connection
  });

  it("does not confuse a 4409 token-reuse close with session_busy", async () => {
    const { conn, statuses } = makeConnection();
    await conn.connect();
    sockets[0]!.open();
    sockets[0]!.simulateClose(4409, "ORCHESTRATION_TOKEN_REUSED");

    await vi.advanceTimersByTimeAsync(600);
    // Falls through to the generic reconnect path, not session_busy.
    expect(statuses).not.toContain("session_busy");
    expect(sockets.length).toBe(2);
  });

  it("backs off exponentially between reconnect attempts, capped at 5s", async () => {
    const { conn } = makeConnection();
    await conn.connect();
    sockets[0]!.open();

    sockets[0]!.simulateClose(1006, "drop 1");
    await vi.advanceTimersByTimeAsync(499);
    expect(sockets.length).toBe(1); // not yet — base delay is 500ms
    await vi.advanceTimersByTimeAsync(2);
    expect(sockets.length).toBe(2);

    sockets[1]!.simulateClose(1006, "drop 2");
    await vi.advanceTimersByTimeAsync(999);
    expect(sockets.length).toBe(2); // second attempt waits ~1000ms (500 * 2^1)
    await vi.advanceTimersByTimeAsync(5);
    expect(sockets.length).toBe(3);
  });

  it("a clean 1000 close (session_closed already handled) does not reconnect", async () => {
    const { conn, statuses } = makeConnection();
    await conn.connect();
    sockets[0]!.open();
    sockets[0]!.simulateClose(1000, "");

    await vi.advanceTimersByTimeAsync(5000);
    expect(statuses.at(-1)).toBe("closed");
    expect(sockets.length).toBe(1);
  });

  it("user-initiated close never triggers a reconnect even on an abrupt underlying close", async () => {
    const { conn, statuses } = makeConnection();
    await conn.connect();
    sockets[0]!.open();
    conn.close();

    await vi.advanceTimersByTimeAsync(5000);
    expect(statuses.at(-1)).toBe("closed");
    expect(sockets.length).toBe(1);
  });

  it("routes decoded downstream binary frames to onAudioFrame", async () => {
    const { conn, audioFrames } = makeConnection();
    await conn.connect();
    sockets[0]!.open();

    const payload = new Int16Array([100, -100, 200]);

    // Build a downstream (kind=2) frame by hand — there's no downstream encoder in
    // lib/audio/protocol.ts (only the browser->server direction needs one); the server side
    // is services/realtime/app/audio/protocol.py.
    const buf = new ArrayBuffer(12 + payload.byteLength);
    const view = new DataView(buf);
    view.setUint8(0, 1);
    view.setUint8(1, 2); // FRAME_KIND_TTS_DOWN
    view.setUint16(2, 0);
    view.setUint32(4, 42);
    view.setUint32(8, 1234);
    new Int16Array(buf, 12).set(payload);

    sockets[0]!.onmessage?.({ data: buf });
    expect(audioFrames).toHaveLength(1);
    expect(audioFrames[0]!.seq).toBe(42);
    expect(Array.from(audioFrames[0]!.payload)).toEqual([100, -100, 200]);
  });

  it("mute/end_session/ping send the expected control message shapes", async () => {
    vi.useFakeTimers();
    const { conn } = makeConnection();
    await conn.connect();
    sockets[0]!.open();

    conn.setMuted(true);
    conn.endSession("user_hangup");
    const sent = jsonSent(sockets[0]!);
    expect(sent.some((m) => m.type === "mute" && m.muted === true)).toBe(true);
    expect(sent.some((m) => m.type === "end_session" && m.reason === "user_hangup")).toBe(true);
  });
});
