# Phase 1 — BUILD — The voice loop (days 4–8)

Build specification for Claude Code. Read `CLAUDE.md` and `docs/03-realtime-protocol.md` first.

**Exit criterion (the Day 8 gate):** a full spoken conversation works from a command-line
harness with per-stage latency recorded. **No web UI is built in this phase.** If a task in
this file seems to need React, you have misread it.

**Rule for this phase:** one task per session, and the protocol freezes at the end of Task 1.2.

---

## TASK 1.1 — Realtime service skeleton and session pinning

FastAPI at port 8080. **Stateful.** One WebSocket per session.

### Requirements

- `GET /health` (no dependencies) and `GET /health/ready` (checks that the ASR model is
  resident and the VAD session is loaded).
- `WS /ws?token=<ws_token>` — the only socket endpoint.
- **Handshake sequence**, in this exact order:
  1. Validate the WS token: signature (using `WS_TOKEN_SECRET`), `exp`, and `jti` present in
     Redis. Burn the `jti` immediately on success.
  2. Load the session row; reject unless `status ∈ {created, active}` and the token's
     `user_id` matches the session owner.
  3. Check the concurrent-session cap; reject with `RATE_LIMITED` if exceeded.
  4. Accept the upgrade. Register the session in an in-process `SessionRegistry`.
  5. Wait for the client's `hello`; validate `protocol_version` major matches; validate
     `client_sample_rate == 16000` and `client_frame_ms == 20`.
  6. Send `ready`.
- **Reject the upgrade before accepting it** when auth fails. Do not accept and then close —
  that leaks the fact that the endpoint exists and makes client error handling ambiguous.
- Model loading happens **once at process startup**, not per session. A `WhisperModel` and an
  ONNX VAD session are process-global and shared. Piper voices are lazily loaded and cached by
  `voice_id`.
- `structlog` contextvars bind `session_id` on connect. Never thread it through signatures.

### Session pinning and lifecycle

- `SessionRegistry: dict[UUID, SessionRuntime]` held in process memory.
- `SessionRuntime` owns: the socket, the audio ring buffer, the state machine, the ASR
  decoder state, the persona history, the question plan, and the per-stage timers.
- On disconnect, the runtime is **retained for 90 seconds** to allow `resume`. After that it
  is finalised: flush buffers, upload the recording, mark the session `closed` with
  `end_reason = user_abandoned`, enqueue the report job.
- A background sweeper runs every 15 s to finalise expired runtimes. It must be idempotent —
  finalising twice must not produce two report jobs.

### Edge cases

| Case | Required behaviour |
|---|---|
| Token reused | Reject upgrade, `ORCHESTRATION_TOKEN_REUSED` |
| Token for a `closed` session | Reject, `NOT_FOUND` |
| Second socket for a live session | Reject the new one with `ORCHESTRATION_SESSION_BUSY`; the existing socket is authoritative |
| `hello` never arrives within 5 s | Close with `ORCHESTRATION_HANDSHAKE_TIMEOUT` |
| Protocol major mismatch | `error` with `fatal: true`, then close |
| Process restart mid-session | Client's `resume` finds no runtime → `error` code `ORCHESTRATION_SESSION_LOST`, `fatal: true`. Session is marked `failed`. Do not pretend to resume. |

### Acceptance criteria

- [ ] Handshake completes in < 200 ms with the model already resident
- [ ] Token reuse, wrong owner, expired token and closed session are each rejected with the
      correct code — one test per case
- [ ] Killing the socket and reconnecting within 90 s resumes the same runtime
- [ ] Killing the socket and reconnecting after 90 s gets `ORCHESTRATION_SESSION_LOST`
- [ ] Two processes never both hold the same session (test the registry rejection path)
- [ ] Memory does not grow across 20 sequential connect/disconnect cycles

---

## TASK 1.2 — Audio capture and the binary protocol ⚠️ FREEZES ON COMPLETION

### 1.2a — Browser capture (AudioWorklet)

Create `apps/web/public/worklets/capture-processor.js` and a thin `lib/audio/capture.ts`
wrapper. **No React yet** — this is a plain TS module the CLI-era test page can drive.

Worklet requirements:
- `process()` **must always return `true`.** Returning `false` tears the node down silently.
- **Preallocate** the ring buffer in the constructor. No allocation inside `process()`.
- Resample from `sampleRate` (the worklet global, usually 48000) to 16000. Integer-ratio
  decimation is acceptable and must be documented in `docs/decisions/`. Non-integer ratios
  use linear interpolation.
- Accumulate into 320-sample (20 ms) frames; emit via `port.postMessage(buf, [buf])` —
  **transferable, not copied**.
- Emit a separate low-rate (`~20 Hz`) RMS amplitude message for the level meter. The meter is
  a P0 non-negotiable and must not be computed on the main thread.

`getUserMedia` constraints: `echoCancellation: true`, `noiseSuppression: true`,
`autoGainControl: true`, `channelCount: 1`.

Float32 → Int16 conversion **must clamp** to [−1, 1] before scaling. Unclamped values wrap and
produce a loud click that sounds like a hardware fault.

### 1.2b — Binary frame format (FROZEN)

```
offset  size  field
0       1     version        uint8, currently 1
1       1     kind           uint8: 1 = mic PCM up, 2 = TTS audio down
2       2     reserved       uint16, zero
4       4     seq            uint32 big-endian, monotonic per direction
8       4     timestamp_ms   uint32 big-endian, relative to session start
12      n     payload        Int16 PCM little-endian
```

- Upstream payload is always exactly 640 bytes (320 samples @ 16 kHz).
- Downstream payload is variable-length TTS audio at a **single fixed rate** (24000 Hz);
  everything is resampled server-side before it leaves.
- JSON control messages travel as **text frames** on the same socket, validated against the
  generated Pydantic models from Task 0.3.

### 1.2c — Server ingest

- Validate frame length: upstream must be exactly 652 bytes. Anything else → `error`
  `CAPTURE_FRAME_MALFORMED`, and drop the frame (do not close the socket for one bad frame).
- Detect sequence gaps. A gap of 1–5 frames is logged and tolerated (fill with silence). A gap
  > 5 frames emits a `degraded` message with `component: "transport"`.
- Write raw PCM to a per-session WAV on disk as it arrives, so a crash never loses the
  recording. Upload begins **during** the session, not at the end.
- Enforce a maximum ingest rate; a client sending faster than real time is either broken or
  hostile. Cap and log.

### 1.2d — Freeze

On completion, write `docs/03-realtime-protocol.md` documenting the frame format, every
message type, sequencing, resume semantics and error codes. Add a CI test asserting the
constants (`16000`, `20`, `1`, header layout) have not changed.

**From this point, changing any of it is a versioned migration with a bumped
`protocol_version`, not a refactor.**

### Acceptance criteria

- [ ] Browser captures 5 continuous minutes with **zero** dropped frames (verified by sequence
      numbers, not by ear)
- [ ] Server writes a WAV that plays back at correct pitch and speed
- [ ] A frame of the wrong length is rejected without killing the session
- [ ] A simulated 3-frame gap is tolerated; a 20-frame gap raises `degraded`
- [ ] Level meter updates at ≥ 20 Hz and reads zero on a muted mic
- [ ] React re-renders at 60 fps in a stress test cause no audio glitches
- [ ] `docs/03-realtime-protocol.md` exists and the CI constant test passes

---

## TASK 1.3 — VAD and the endpointing cascade

### 1.3a — Silero VAD

- ONNX Runtime, CPU, single-threaded session. Load once at startup.
- Silero expects **512-sample windows at 16 kHz**. Your frames are 320 samples. Maintain an
  accumulator and run inference on each complete 512-sample window; do not resize the frame.
- Output is a speech probability per window. Apply **hysteresis**, not a single threshold:
  - onset when probability > `0.5` for 2 consecutive windows,
  - offset when probability < `0.35` for the full silence window.
  A single threshold produces rapid flapping at the boundary.
- Must run in **< 3 ms per window** on CPU. Assert this in a test; if it fails, the whole
  design is at risk.

### 1.3b — The cascade

Implement as a pure, testable function. **No IO except the optional step 5.**

```python
def should_endpoint(state: EndpointState) -> EndpointDecision:
    """Returns END, CONTINUE, or NEEDS_SEMANTIC_CHECK."""
```

Order, cheapest first:

1. **Acoustic silence.** Speech probability below threshold for a continuous window.
   Base `ENDPOINT_BASE_SILENCE_MS` (500).
2. **Adaptive threshold.** Per speaker, derived from the distribution of pauses observed
   *within* their completed utterances this session. Use ~p90 of that distribution, clamped to
   `[ENDPOINT_MIN_SILENCE_MS, ENDPOINT_MAX_SILENCE_MS]` = [350, 900]. Fall back to the base
   value until at least 3 utterances have been observed.
3. **Filler suppression.** If the transcript tail matches a hesitation marker
   (`um|uh|erm|hmm|so|like|and|but|you know|I mean`), extend the window by 300 ms.
   Cap total extensions at 2 per utterance so a filler-heavy speaker is not held forever.
4. **Syntactic incompleteness.** Regex, **not a model**. A trailing coordinating conjunction,
   preposition or article suppresses endpointing and extends by 250 ms. Same extension cap.
5. **Semantic completeness check.** Runs *only* when the window elapsed but steps 3–4 flagged
   the transcript as unfinished. One binary question to `MODEL_ENDPOINTER` with a hard
   **80 ms** timeout (`SEMANTIC_ENDPOINT_TIMEOUT_MS`). **On timeout, END the turn** — a
   slightly early cut beats an unbounded wait. This step is cuttable (see the cut order).

### 1.3c — Guards

- **Minimum utterance length** `ENDPOINT_MIN_UTTERANCE_MS` (400): a shorter detection is noise,
  discarded, state returns to `idle` without creating a turn.
- **Maximum turn length** `ENDPOINT_MAX_TURN_MS` (120000): the persona interrupts. Log this as
  `persona_interrupt`, not as an error.

### 1.3d — The boundary dataset ⚠️ DAY 5, NOT DAY 19

Build `scripts/collect_boundaries.py`:

- Records real speech (yours, and anyone you can borrow) into `data/boundaries/`.
- A simple terminal or minimal-HTML review tool that plays each utterance and lets a human
  mark the true end-of-speech sample index.
- Output: `data/boundaries/labels.jsonl` with `{audio_path, true_end_ms, notes}`.
- **Target: ≥ 200 hand-marked boundaries.** Include deliberately hard cases: mid-sentence
  thinking pauses, trailing fillers, lists with pauses between items, and false starts.

Then `scripts/eval_endpointing.py` computes, against that set:
- **precision** — of ends the system called, the fraction where the speaker had genuinely
  finished,
- **recall** — the fraction of true ends detected at all,
- **latency** — ms after the true boundary, at p50/p95.

This script is used on day 11 to tune. **Tune against this set, never against feeling.**

### Edge cases

| Case | Required behaviour |
|---|---|
| Cough / door slam | Below min utterance length → discarded, no turn |
| Speaker pauses 800 ms mid-sentence | Adaptive threshold + syntax rule should hold; test explicitly |
| Speaker says "um…" and stops for 2 s | Ends after the extension cap, does not hold forever |
| Continuous background noise | VAD never reports silence → max turn length fires, persona interrupts |
| Semantic model unreachable | Timeout path ends the turn; `degraded` **not** raised (this is an optional component) |
| User never speaks at all | After 20 s of silence in `idle`, the persona prompts (SP-09) |

### Acceptance criteria

- [ ] VAD runs in < 3 ms per 512-sample window on CPU (asserted in a test)
- [ ] The cascade is a pure function with ≥ 15 unit tests covering every row above
- [ ] ≥ 200 hand-marked boundaries committed with the collection script
- [ ] `eval_endpointing.py` reports precision, recall and latency percentiles
- [ ] Hysteresis prevents flapping (test with audio at the threshold boundary)
- [ ] Extension caps prevent unbounded holding

---

## TASK 1.4 — Streaming ASR

### Requirements

- `faster-whisper`, model from `ASR_MODEL` (default `base.en`), `compute_type=int8`, CPU.
- **One model instance per process**, shared. Transcription runs in a thread pool
  (`asyncio.to_thread`) — it is CPU-bound and will block the event loop otherwise. This is the
  single most important line in this task.
- **Partial hypotheses:** every 500 ms during `listening`, re-transcribe the buffered utterance
  with `beam_size=1` and emit `partial_transcript` with a stability score. Partials are
  cosmetic; never let a partial pass block the audio ingest path.
- **Final pass:** on endpointing, transcribe once with `beam_size=5`, `word_timestamps=True`,
  `condition_on_previous_text=False`, and `initial_prompt` built from scenario tags + resume
  nouns + persona-mentioned terms.
- Punctuation and casing restoration, word-level timings, and `asr_confidence` (mean segment
  logprob mapped to 0–1) written to the `turns` row.

### Real-time factor

- Measure RTF on every final pass and write it to `latency_events` as stage `asr_finalize`
  alongside a `metadata.rtf` value.
- If RTF > 0.8 over a rolling window of 5 turns, **automatically downgrade** to `tiny.en` and
  emit `degraded` with `component: "asr"`, `recoverable: true`. Log the switch. Never silently
  degrade quality without recording it.

### Deterministic delivery features (SP-10)

Computed here, from timings only, **never from a model**, and written to `turn_metrics`:
`wpm`, `filler_count`, `filler_rate`, `longest_pause_ms`, `speech_ratio`, `word_count`.

Filler list is a config constant, not inline: `um, uh, erm, ah, like, you know, I mean, sort
of, kind of, basically, actually, literally`. Count only standalone-token matches — "like" in
"a system like Kafka" is not a filler and a naive substring match will over-count badly.

### Confidence gating (SP-08)

If `asr_confidence < 0.55`, do **not** send the transcript to the persona as if it were
reliable. Instead the persona produces a scenario-appropriate clarification — "Sorry, the line
broke up there, say that again?" — from a pre-written pool. A confidently wrong reply to a
misheard question is far worse than asking again.

### Edge cases

| Case | Required behaviour |
|---|---|
| Empty transcript on a real utterance | Discard, return to `listening`, do not create a turn |
| Whisper repetition loop | `condition_on_previous_text=False` prevents it; a test asserts no token repeats > 8× |
| Utterance longer than 30 s | Chunk to 30 s windows with 2 s overlap; stitch on word timings |
| Model file missing at startup | Fail fast at boot with a clear message; never start half-loaded |
| Transcription raises mid-turn | `degraded` with `component: "asr"`; persona gets a clarification prompt; session continues |

### Acceptance criteria

- [ ] Partials appear within 600 ms of speech onset and update continuously
- [ ] Final transcript available < 180 ms (p95) after endpointing fires
- [ ] Word timestamps present on every final transcript and monotonically increasing
- [ ] RTF measured and logged per turn; auto-downgrade tested by forcing a slow model
- [ ] Delivery metrics match hand-computed values on a committed fixture, exactly
- [ ] `initial_prompt` biasing measurably improves recognition of a technical-term fixture
      (a test asserts a specific term is recognised with biasing and not without)
- [ ] Transcription never blocks the event loop (asserted: frames continue to ingest during a
      forced slow transcription)

---

## TASK 1.5 — Synthesis, chunking and playback

### 1.5a — Sentence chunker

Pure function, heavily tested. Consumes a token stream, yields chunks.

Rules:
- Split at sentence terminators `. ! ?` and at clause boundaries `, ; :` **only when** the
  accumulated chunk is ≥ 3 words.
- **Never split** inside: known abbreviations (`Dr. Mr. Mrs. e.g. i.e. etc. vs. approx.`),
  numbers (`99.9`), version strings (`v1.2.3`), decimals, or unclosed quotes/brackets.
- Collapse ellipses; never emit an empty chunk.
- **First chunk is deliberately short** — emit at the first valid boundary even if a longer
  chunk would sound better. Cap the first chunk at ~12 words; force emission at that point.
- Force-flush any remainder when the token stream ends.

Write one unit test per row of this table:

| Input | Expected chunks |
|---|---|
| `Dr. Smith joined in 2019.` | 1 |
| `We hit 99.9% uptime. Then it broke.` | 2 |
| `So, tell me about it.` | 1 (leading clause < 3 words merges) |
| `He said "yes." Then he left.` | 2, split after the closing quote |
| `Running v1.2.3 in prod.` | 1 |
| `e.g. Kafka, Redis, and Postgres.` | 1 |
| `Well... I think so.` | 1 |
| 40 words with no punctuation | force-split at the word cap |

### 1.5b — Piper synthesis

- Voice loaded lazily by `voice_id`, cached per process.
- Synthesis runs in a thread pool. Read the output sample rate from the voice's `.json`
  (22050) and **resample server-side to a single fixed 24000 Hz** before sending. Never send
  mixed rates downstream.
- **Deadline per chunk.** If a chunk takes > 400 ms to synthesise, fall back to the secondary
  voice; if that also fails, emit a pre-synthesised canned holding line and raise `degraded`
  with `component: "tts"`.
- **Backchannel cache (TS-07):** pre-synthesise a small pool of short acknowledgements
  ("mm-hm", "right", "okay", "sure") **per voice at startup** and hold them in memory for
  zero-latency playback. Used by latency masking in Phase 2.

### 1.5c — Browser playback

- `AudioContext` at 24000 Hz. Decode incoming Int16 chunks to `AudioBuffer`.
- **Schedule against `ctx.currentTime`**, not `setTimeout`:
  `startAt = max(ctx.currentTime + JITTER_BUFFER_MS/1000, nextStartTime)`.
- Keep every `AudioBufferSourceNode` handle in a queue so stop-on-speech can kill all of them.
- **Never use an `<audio>` element.** It cannot gaplessly concatenate.
- Adaptive jitter buffer: start at `JITTER_BUFFER_MS` (120), grow by 40 ms on each observed
  underrun, never shrink below 60 ms.

### 1.5d — Stop-on-speech (TS-09)

On sustained user speech during `speaking` (guard interval 250 ms of voiced frames):
1. Stop all scheduled sources immediately and clear the queue.
2. Send `interrupted` with the truncated text.
3. Write the persona turn with `truncated = true` and the text actually spoken (estimate from
   chunks that started playing, not from chunks generated).
4. Transition `speaking → interrupted → listening`.

The distinction in (3) matters: a chunk generated but never played was never heard, and
recording it as spoken corrupts both the transcript and the scoring context.

### Edge cases

| Case | Required behaviour |
|---|---|
| Chunk arrives out of order | Reorder by `seq`; drop anything older than the playhead |
| Client can't keep up (backpressure) | **Drop the oldest queued chunk**, never buffer unboundedly |
| Voice file missing | Fail at startup for the default voice; for a persona voice, fall back to default + log |
| User speaks for 200 ms then stops | Under the guard interval → not an interruption, playback continues |
| Persona reply is a single word | Chunker emits one chunk; no clipping |
| Synthesis produces zero-length audio | Skip the chunk, log, continue — never send a zero-length frame |

### Acceptance criteria

- [ ] Chunker passes every row of the table above
- [ ] First audio chunk leaves the server < 250 ms (p95) after the first token arrives
- [ ] Playback of a 6-chunk reply has **no audible gap** (verify by concatenating the received
      audio and inspecting for discontinuities, not only by ear)
- [ ] Stop-on-speech halts audio within one buffer window
- [ ] Truncated persona turns record only what actually played
- [ ] Forcing a TTS timeout produces a spoken fallback, not a dead session
- [ ] Backchannel pool loaded at startup for every configured voice

---

## TASK 1.6 — Close the loop: the CLI harness and latency instrumentation

**This is the Day 8 gate. Everything above exists to make this work.**

### 1.6a — Latency instrumentation (write this FIRST, not last)

```python
@asynccontextmanager
async def stage(session_id, turn_id, name: StageName, **metadata):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        await emit_latency_event(session_id, turn_id, name,
                                 duration_ms=(time.perf_counter()-t0)*1000,
                                 metadata=metadata)
```

- Fixed stage enum: `endpoint_detect`, `asr_finalize`, `prompt_assemble`, `model_ttft`,
  `first_chunk_assemble`, `tts_first_chunk`, `transport`, `e2e`.
- **No sampling.** Every stage, every turn.
- Writes are **batched and fire-and-forget** — a latency write must never itself add latency.
  Buffer in memory, flush every 2 s or 50 rows, and flush on session close.
- `e2e` is measured from the frame timestamp of the last voiced frame to the moment the first
  downstream audio byte is written to the socket. Not from any intermediate point.
- Every model invocation writes a `model_calls` row: role, model, prompt version, tokens in
  and out, TTFT, total latency, cost, cache status. No exceptions.

### 1.6b — The CLI harness (`make cli`)

`scripts/cli_session.py` — the tool you will use to debug for the next three weeks.

```
$ make cli SCENARIO=backend-system-design DIFFICULTY=standard

  ✓ session created  · 018f2a...
  ✓ ws connected     · warm-up 180ms
  ♪ [persona] "Thanks for making the time. Before we get into design —
               walk me through the hardest thing you shipped this year."

  ● listening... ▁▃▅▇▅▃▁   (level meter)
  › you: "So last quarter I rebuilt the ingestion pipeline, um, the one
          that was backing up under load"

  ┌─ turn 1 ──────────────────────────────────────────┐
  │ endpoint_detect        412 ms                     │
  │ asr_finalize            94 ms                     │
  │ prompt_assemble         11 ms                     │
  │ model_ttft             287 ms                     │
  │ first_chunk_assemble    63 ms                     │
  │ tts_first_chunk        141 ms                     │
  │ transport              108 ms                     │
  │ ─────────────────────────────────────             │
  │ e2e                   1043 ms   ✅ (budget 1100)  │
  └───────────────────────────────────────────────────┘
```

Requirements:
- `sounddevice` for capture and playback; same binary protocol as the browser will use.
- Prints the stage table after every turn with a pass/fail against the budget.
- `--replay <wav>` mode feeds a committed fixture instead of the microphone, so latency runs
  are reproducible and can go in CI.
- `--persona-stub` mode uses a fixed canned reply, isolating pipeline latency from model
  latency. Use this to prove the pipeline before blaming the model.
- Prints a session summary on exit: p50/p95 per stage and end-to-end, turn count, RTF.

### 1.6c — Minimal persona (deliberately trivial)

A single-layer prompt, no question plan, no difficulty ladder — **all of that is Phase 2**.
Just enough to produce a short in-character reply so the loop closes. Resist improving it here.

### Acceptance criteria — THE GATE

- [ ] A 5-minute spoken conversation completes from the CLI with no crash
- [ ] Stage timings print after every turn and are written to `latency_events`
- [ ] End-to-end p50 measured and reported (it need not hit 1100 ms yet — day 11 is for that)
- [ ] `--replay` mode is deterministic across runs
- [ ] `--persona-stub` isolates pipeline latency from model latency
- [ ] Session summary prints correct percentiles
- [ ] The recording is uploaded and playable
- [ ] Killing the network mid-session and restoring it resumes the conversation

> **If these boxes are not all ticked, do not proceed to Phase 2 and absolutely do not
> proceed to Phase 3.** Fix the pipeline. The build plan has slack for this; the UI phases
> do not.

---

## Phase 1 definition of done

- [ ] AudioWorklet capture, 5 minutes, zero dropped frames
- [ ] Binary protocol frozen, documented, constant-tested in CI
- [ ] Silero VAD < 3 ms/window with hysteresis
- [ ] Endpointing cascade implemented as a pure function with full unit coverage
- [ ] **≥ 200 hand-marked boundaries committed**, evaluation script working
- [ ] Streaming ASR with partials, word timestamps, RTF monitoring and auto-downgrade
- [ ] Deterministic delivery metrics exact against a fixture
- [ ] Chunker passing every edge case; Piper streaming; gapless scheduled playback
- [ ] Stop-on-speech working, truncation recorded correctly
- [ ] Latency instrumentation on every stage of every turn, no sampling
- [ ] **A spoken conversation works from the terminal**
