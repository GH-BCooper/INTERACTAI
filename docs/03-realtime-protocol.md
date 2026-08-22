# 03 — Realtime protocol (FROZEN as of Task 1.2d)

This document is the frozen contract between a client (browser or the CLI harness) and
`services/realtime`. Everything below is enforced by `tests/unit/realtime/test_protocol_frozen.py`
(the binary frame constants) and by the generated Pydantic/TypeScript types in
`packages/schema/ws-messages.schema.json` (the JSON control messages). **Changing anything
here is a versioned migration — bump `protocol_version`'s major component and negotiate it in
`hello`/`ready` — never a refactor** (CLAUDE.md §1.3).

## 1. Transport

One WebSocket per session: `WS /ws?token=<ws_token>`. The socket carries two kinds of frames:

- **Binary frames** — raw PCM audio, upstream (mic) and downstream (persona speech), header
  format below.
- **Text frames** — JSON control messages, one discriminated union
  (`packages/schema/ws-messages.schema.json`), validated by the generated Pydantic models
  server-side and TypeScript types client-side.

The two are interleaved freely on the same socket; there is no separate audio channel.

## 2. The audio contract (frozen since day 4)

| | Upstream (mic → server) | Downstream (server → client) |
|---|---|---|
| Sample rate | 16000 Hz | 24000 Hz |
| Channels | 1 (mono) | 1 (mono) |
| Format | Int16 PCM, little-endian | Int16 PCM, little-endian |
| Frame size | exactly 320 samples (20ms) | variable (one TTS chunk's audio) |

Upstream is fixed-size by construction (the AudioWorklet only ever emits 320-sample frames).
Downstream is resampled server-side to 24000 Hz before it ever leaves the process — the client
never has to handle more than one playback rate.

## 3. Binary frame header

Every binary frame — both directions — starts with the same 12-byte header:

```
offset  size  field          type
0       1     version        uint8, currently 1 (PROTOCOL_VERSION)
1       1     kind           uint8: 1 = mic PCM up, 2 = TTS audio down
2       2     reserved       uint16, always 0
4       4     seq            uint32 big-endian, monotonic per direction
8       4     timestamp_ms   uint32 big-endian, relative to session start
12      n     payload        Int16 PCM, little-endian
```

- `seq` is a per-direction, per-connection monotonic counter starting at 0. The two directions
  keep independent counters — the client's upstream `seq` and the server's downstream `seq`
  are unrelated.
- `timestamp_ms` on upstream frames is derived from the sample count the capture worklet has
  emitted so far (`frameIndex * 20`), not wall-clock arrival time — see
  `docs/decisions/0004-worklet-resampling.md` for why that's the more honest clock.
- Upstream payload is **always exactly 640 bytes** (320 samples × 2 bytes) — total frame size
  **652 bytes**, exactly. Any other length is `CAPTURE_FRAME_MALFORMED` (§6).
- Downstream payload length varies with the TTS chunk; each downstream binary frame is preceded
  by an `audio_chunk_meta` text message carrying the same `byte_length` so the client can
  validate what it received.

Reference implementations: `services/realtime/app/audio/protocol.py` (Python, canonical) and
`apps/web/lib/audio/protocol.ts` (TypeScript, mirrors it byte-for-byte —
`tests/unit/realtime/test_protocol_frozen.py` and `apps/web/lib/audio/protocol.test.ts` both
assert the constants independently).

## 4. Handshake sequence

1. Client opens `WS /ws?token=<ws_token>`. The token is minted by the API
   (`POST /sessions/{id}/ws-token`), HS256-signed with `WS_TOKEN_SECRET`, single-use, 120s TTL.
2. Server validates the token (signature, `exp`, `jti` present in Redis) and burns the `jti`
   immediately — a second presentation of the same token is `ORCHESTRATION_TOKEN_REUSED`.
3. Server loads the session row; rejects unless `status ∈ {created, active}` and the token's
   `user_id` matches the session owner (both collapse to `NOT_FOUND` — confirming a session
   exists to a non-owner is its own leak).
4. Server checks capacity (`MAX_CONCURRENT_SESSIONS`) and this-session exclusivity (only one
   live socket per session_id) — both pre-accept.
5. **Only once all of the above pass does the server accept the WebSocket upgrade.** A
   rejection never accepts-then-closes; it closes without accepting, carrying the reason as a
   WS close code + reason string (there is no open socket yet to send a JSON `error` on) —
   see §6's close-code table.
6. Server registers the session in its in-process `SessionRegistry` and waits (5s timeout) for
   the client's first message: `hello` (fresh) or `resume` (reconnect).
7. Server validates `hello.protocol_version`'s major component and
   `client_sample_rate == 16000` / `client_frame_ms == 20`, mismatch → fatal
   `ORCHESTRATION_PROTOCOL_MISMATCH`.
8. Server sends `ready` and transitions its internal state machine `connecting → idle`.

## 5. Server state machine

Eight states (`ServerMachineState`), defined in `docs/decisions/0001-realtime-state-machine.md`
and implemented in `services/realtime/app/state_machine.py`:

```
connecting → idle ⇄ listening ⇄ endpointing → thinking → speaking → idle
                 ↘________________________________________________↗ (any → degraded → any)
                                                            (any → closed, terminal)
```

Every transition is validated (`IllegalTransitionError` on anything not in the table) and
tested exhaustively — one legal and one illegal case per state
(`tests/unit/realtime/test_state_machine.py`). The client only ever sees the 4-value
`client_state` collapse (`listening · thinking · speaking · degraded`) carried alongside each
`state_change` message — `connecting`, `idle` and `endpointing` all render as "listening" since
there is no user-visible difference between "not talking yet" and "deciding if you're done."

`interrupted` and `closing` are **not** separate states (they appear in
`docs/phase-1-LEARN.md`'s illustrative table but not in the frozen schema): a stop-on-speech
interrupt is the `speaking → listening` edge plus an `interrupted` *message*; closing is an
internal finalisation flag, not a broadcast state.

## 6. Errors, close codes, and edge cases

Every JSON `error` message (sent once the socket is open) has the frozen shape:

```json
{ "type": "error", "seq": 12, "code": "CAPTURE_FRAME_MALFORMED", "message": "...",
  "recovery": "...", "fatal": false, "trace_id": "..." }
```

Pre-accept rejections have no open socket to send that on, so they use a WS close code plus a
short reason string carrying the same `code`:

| Case | Close code | `code` string | Fatal |
|---|---|---|---|
| Missing/invalid/expired token | 4401 | `AUTH_INVALID_TOKEN` | yes |
| Token already used | 4409 | `ORCHESTRATION_TOKEN_REUSED` | yes |
| Session not found / wrong owner / closed | 4404 | `NOT_FOUND` | yes |
| Second socket for a live session | 4409 | `ORCHESTRATION_SESSION_BUSY` | yes |
| Concurrent-session cap exceeded | 4429 | `RATE_LIMITED` | yes |

Post-accept errors (socket already open, sent as `error` then closed with WS code 1008):

| Case | `code` |
|---|---|
| No `hello`/`resume` within 5s | `ORCHESTRATION_HANDSHAKE_TIMEOUT` |
| Protocol major mismatch or audio-contract mismatch | `ORCHESTRATION_PROTOCOL_MISMATCH` |
| `resume` for a runtime the process no longer holds (restart) | `ORCHESTRATION_SESSION_LOST` |

Non-fatal, doesn't close the socket:

| Case | Handling |
|---|---|
| Malformed upstream frame (wrong length/version/kind) | `error` `CAPTURE_FRAME_MALFORMED`, frame dropped, socket stays open |
| 1-5 frame sequence gap | Silence-filled in the recording, tolerated silently |
| >5 frame sequence gap | `degraded` message, `component: "transport"` |
| Client sending faster than real time | Frame silently dropped (token-bucket rate limiter) |

## 7. Resume semantics

- On an unexpected disconnect (`WebSocketDisconnect`, not a client-sent `end_session`), the
  runtime is retained in-process for **90 seconds** (`resume_grace_s`), not finalised.
- A background sweeper runs every 15s and finalises any runtime past its grace window; this is
  idempotent by construction (`SessionRegistry.finalize`) — a runtime already finalised is a
  no-op even if the sweeper and another path both try.
- To resume, the client requests a **new** ws-token for the same session (tokens are
  single-use) and reconnects. The pre-accept handshake recognises a disconnected-but-not-yet-
  finalised runtime for that session_id and offers `resume` instead of `hello`; the client must
  send `resume` (carrying `last_server_seq`/`last_client_seq`) as its first message.
- **What resume does not yet do**: replay of individual missed binary frames by sequence
  number. Reattaching the same `SessionRuntime` (state machine, turn history, adaptive
  threshold tracker) is what "resumes the conversation" — frame-level replay of exactly what
  was missed during the drop is a known gap, not implemented in Phase 1.
- If the process restarted (the runtime is gone, not just disconnected), `resume` gets
  `ORCHESTRATION_SESSION_LOST`, `fatal: true`. The client must start a new session — this is a
  deliberate refusal to pretend a resume that can't actually happen.

## 8. Message types

All 17 come from `packages/schema/ws-messages.schema.json`, generating
`services/realtime/app/schemas/ws.py` (Pydantic) and `apps/web/lib/ws-types.ts` (TypeScript).
Client → server: `hello, resume, mute, end_session, ping`. Server → client: `ready,
state_change, partial_transcript, turn_finalized, persona_text, audio_chunk_meta, interrupted,
degraded, latency_report, session_closed, error, pong`.

`audio_chunk_meta` always immediately precedes the binary frame it describes — a client should
never see a downstream binary frame it didn't get metadata for first.

`latency_report` carries whichever of the eight fixed stages
(`endpoint_detect, asr_finalize, prompt_assemble, model_ttft, first_chunk_assemble,
tts_first_chunk, transport, e2e`) were actually measured for that turn — not every stage fires
on every turn (e.g. a `--persona-stub` turn has no `model_ttft`).

## 9. What CI enforces

`tests/unit/realtime/test_protocol_frozen.py` asserts every constant in this document
byte-for-byte (`PROTOCOL_VERSION`, both `FRAME_KIND_*` values, `UPSTREAM_SAMPLE_RATE`,
`UPSTREAM_FRAME_SAMPLES`, `UPSTREAM_PAYLOAD_BYTES`, `HEADER_BYTES`, `UPSTREAM_FRAME_BYTES`,
`DOWNSTREAM_SAMPLE_RATE`), plus header endianness and round-trip encode/decode. A change to any
of them fails that test — which is the point.
