# Progress

## 2026-08-20 — Phase 0: Foundation

Built end to end in one session, all seven tasks. Every acceptance criterion in
`docs/phase-0-BUILD.md` that can be verified by execution was run, not just written —
see the per-task notes below for exactly which.

### What exists now

- **Monorepo skeleton** (0.1): uv workspace (`services/{api,realtime,coach,training}`, each
  `package = false` so they share one venv without top-level `app` name collisions), pnpm
  workspace (`apps/web`, `packages/schema`), ruff + mypy (`--strict` on `services/realtime`
  only) configured at the root.
- **Docker infra** (0.2): `pgvector/pgvector:pg16`, `redis:7-alpine`, `minio` + a `minio-init`
  one-shot bucket creator, all with real healthchecks, host ports overridable.
- **WS schema codegen** (0.3): `packages/schema/ws-messages.schema.json` — a discriminated
  union covering all 17 message types — generates matching Pydantic (`datamodel-code-generator`)
  and TypeScript (`json-schema-to-typescript`) output. Deterministic (byte-identical across
  runs, verified). Round-trip tests for every message type pass in both languages.
- **Database** (0.4): all 15 P0 tables migrated, hand-reviewed (not blind autogenerate) —
  `turns` is genuinely RANGE-partitioned by month. See `docs/decisions/0002-*.md` for why its
  child tables (`turn_metrics`, `turn_scores`, `latency_events`, `model_calls`, `annotations`)
  reference `sessions.id` for their cascade FK rather than a composite FK into `turns` — Postgres
  requires the partition key in any FK target, so those tables get `session_id` (real FK, real
  cascade) plus a plain `turn_id` column (indexed, app-enforced).
- **API service** (0.5): every endpoint in the spec, real GitHub/Google OAuth (implemented
  directly against each provider's HTTP API, not Authlib's session-coupled client, so the CSRF
  `state` can live in Redis as specified), rotating refresh tokens with theft detection
  (versioned family revocation), single-use WS tokens, Redis rate limiting, the frozen
  `{error:{code,message,recovery,fatal,trace_id}}` shape on every error path.
- **Content** (0.6): 9 scenarios (3 families × 3 difficulties), 4 personas (one per
  temperament), 2 rubrics — 15 criteria, 75 anchor descriptors, all passing
  `scripts/validate_content.py`. `make seed` is idempotent (verified: 3 consecutive runs,
  stable row counts).
- **Tests + CI** (0.7): 66 Python tests + 2 vitest tests, all passing against real
  testcontainers Postgres/Redis (never mocked). Audio fixtures in `tests/fixtures/audio/` —
  see that directory's README for an important caveat. `.github/workflows/ci.yml` has the five
  required jobs.

### Decisions I made without being told, and why

Two decision docs in `docs/decisions/` — not disagreements with the spec, just places where
the spec (or the missing `docs/02-19` files) left a genuine gap:

- **`0001-realtime-state-machine.md`** — the WS schema needed the 8 server states / 4 client
  states now, but `docs/04-state-machine.md` doesn't exist in this repo. Defined a reasonable
  set; it's schema-versioned, so a Phase 1 correction is a tracked diff, not a silent rewrite.
- **`0002-turns-partitioning-and-fk.md`** — the partitioned-table-vs-FK conflict described above.

Smaller calls, not written up as formal decisions: `APP_SECRET` is used as a pepper for
refresh-token secret hashing; OAuth account linking by email when a user signs in with a second
provider; scenarios carry the *full* difficulty_params lookup table (not just their own tier)
so difficulty is a runtime choice independent of which brief variant was opened.

### What I could not verify by running it

- **The actual GitHub/Google OAuth browser round trip.** Everything downstream of a verified
  `OAuthUserInfo` — user creation/linking, token issuance, refresh rotation, cascade delete — is
  tested. The provider handshake itself needs a human in a browser. `.env` already has real,
  distinct client IDs/secrets for both.
- **`GET /health/ready` returning 503 with Postgres actually stopped.** The failure-path logic
  (catch, log, report false, set 503) is simple and code-reviewed; I didn't want to stop the
  shared dev Postgres mid-session to prove it.
- **Audio fixtures are synthetic (Piper TTS), not recorded.** No microphone in this
  environment. See `tests/fixtures/audio/README.md`.

### Environment notes for future sessions

- `make` wasn't installed on this Windows machine; a portable GNU Make 3.81 binary (no
  installer, no admin) was placed in the user's own `~/bin`, which was already first on PATH.
- Windows console codepage mangles em-dashes in anything printed to a terminal (not in file
  content) — runtime `print()`/`echo` strings use a plain hyphen for this reason; comments and
  docstrings don't need to.

### Answers to the interview questions this phase earns (docs/phase-0-LEARN.md §11)

- **Why one backend language?** The hard part of this project is concentrated in one Python
  process (`realtime`) doing VAD/ASR/LLM/TTS streaming under a 1.5s budget. A language boundary
  on that path buys nothing and costs a serialization hop plus a second dependency tree.
- **What does "stateful" force?** `realtime` pins a session to one process for its lifetime
  (open socket, growing ring buffer, resident ASR model, in-flight decoder state) — it can't be
  serverless or sit behind round-robin LB, and needs resume-not-retry semantics on socket drop.
- **How do frontend and backend types stay in sync?** One JSON Schema, two generators, a CI job
  that regenerates and diffs — `schema-drift` fails the build the moment someone forgets.
- **Why a different WS credential from the session token?** A browser `WebSocket` constructor
  can't carry a custom header, so the credential travels in the URL — which lands in proxy logs
  and history. Scoping it to one session, 120s, single-use, and a separate secret means a leaked
  WS token costs one practice session, not an account.
- **Why UUID v7?** Primary keys sort by creation time — `turns` (fastest-growing table) stays
  index-append-mostly instead of fragmenting, and three UUIDs in a log line are orderable on
  sight.
- **Why are `turn_metrics` and `turn_scores` separate tables?** One is arithmetic on timestamps
  and is always correct; the other is a model judgement and is sometimes wrong. Merging them
  invites the UI to show both with equal authority.

## 2026-08-21 — Phase 1: The voice loop

Built end to end in one session, all six tasks plus the Day 8 gate. Per-task acceptance
criteria were run, not just written, wherever real infrastructure made that possible — see
below for exactly what that covers and what it doesn't.

### What exists now

- **Realtime skeleton and session pinning** (1.1): the WS handshake (token validate-and-burn,
  ownership/status check, concurrency cap, pre-accept rejection via close code — never
  accept-then-close), `SessionRegistry`/`SessionRuntime`, the 90s resume grace window, and an
  idempotent 15s sweeper. `services/realtime/app/db/` mirrors the tables it touches as
  SQLAlchemy Core objects rather than importing api's ORM (`docs/decisions/0003`) — api and
  realtime stay independent workspace members.
- **Binary protocol, frozen** (1.2): `services/realtime/app/audio/protocol.py` /
  `apps/web/lib/audio/protocol.ts` mirror each other byte-for-byte, both under CI-enforced
  constant tests. `apps/web/public/worklets/capture-processor.js` does resampling (one
  linear-interpolation algorithm for both integer and non-integer ratios — `docs/decisions/
  0004`), 20ms framing and the RMS level meter entirely on the audio thread. `docs/03-
  realtime-protocol.md` is the frozen spec.
- **VAD and endpointing** (1.3): Silero VAD wrapped correctly against its *actual* undocumented
  contract — it needs a 64-sample context prefix from the previous window (576 samples total,
  not 512) or it silently returns near-zero probability for real speech; found by direct
  experiment, not assumed (see the module docstring in `services/realtime/app/vad/silero.py`).
  The 5-step cascade, the adaptive-threshold tracker, and the two guards are pure functions
  with 30 unit tests. The real semantic-completeness check (step 5) is wired to the actually-
  configured `MODEL_ENDPOINTER` (`ollama/qwen2.5:0.5b-instruct`) and tested live — the model
  is fast but not reliable at 0.5B params, which the cascade is deliberately designed to
  tolerate (fail toward END) rather than paper over with prompt engineering.
- **Boundary dataset** (1.3d): 220 items, synthetic (Piper + exact silence splicing), not real
  hand-marked speech — no microphone or human labeller in this environment, same constraint
  Phase 0 hit for audio fixtures. `scripts/collect_boundaries.py` is the real tool, built and
  ready for a human with a microphone. `scripts/eval_endpointing.py` ran the full simulation
  (real VAD + real ASR transcript tails) against all 220: recall 1.0, precision 0.57 —
  precision is dragged down almost entirely by the `mid_sentence_pause`/`trailing_filler_then_
  continues` cases with gaps longer than the two-extension cap can cover without a live
  semantic check, which is exactly the scenario step 5 exists for. Numbers and caveats are in
  `data/boundaries/eval_report.json` and `data/boundaries/README.md`.
- **Streaming ASR** (1.4): faster-whisper, partials off-thread, final pass chunked at 30s/2s
  overlap, RTF-monitored auto-downgrade, confidence gating with a versioned clarification pool
  (`content/clarifications.yaml`). Vocabulary biasing is proven, not asserted on faith: base.en
  mishears "Spotmies" as "Sputbys" unbiased and gets it right with an `initial_prompt` hint —
  both transcriptions captured in `tests/unit/realtime/test_whisper_asr.py`.
- **Chunker, TTS, playback** (1.5): the sentence chunker passes every row of the spec's table,
  including the one genuinely subtle case (abbreviations don't count toward the clause-split
  word minimum, or `"e.g. Kafka, Redis, and Postgres."` would wrongly split — see the module
  docstring). Piper synthesis, the deadline/fallback/holding-line chain, and the backchannel
  cache are real, but see "what surprised me" below for this machine's actual Piper latency.
  Browser playback's ordering/backpressure/jitter-buffer/interrupt-guard logic is pure and
  tested; the `AudioContext` glue is not (no Web Audio in Node) and needs a real browser check.
- **Latency instrumentation and the CLI harness — the Day 8 gate** (1.6): `LatencyRecorder` is
  batched, fire-and-forget, no sampling. `scripts/cli.py` bootstraps a session by calling api's
  real `session_service.create_session` in-process (no separate `make api` needed), connects
  to a running `make realtime` over the real WS protocol, and closes the loop. **This was run
  for real, repeatedly, against live infrastructure** (`make up`, real Postgres/Redis/MinIO,
  real faster-whisper, real Piper, real Groq for the non-stub persona path) — see below.

### The live end-to-end run, and the four real bugs it found

Getting one clean turn through the real stack surfaced bugs that no unit test caught, because
each one only exists at the seam between components:

1. **The handshake never actually entered `idle`.** `_complete_hello` sent the `ready` message
   but never called `state_machine.transition(idle)` — every frame arrived and was ingested
   (written to disk correctly) but silently never reached the VAD/cascade, because the ingest
   branch only fires in `{idle, listening, endpointing}`. No exception, no log line — it just
   did nothing. Fixed by adding the missing transition.
2. **The rate limiter penalized the server's own jitter, not just a hostile client.** A strict
   "no two frames within 10ms" rule flagged a false `degraded` transport warning the moment
   the server briefly fell behind (a slow synchronous call delaying the next `receive()`)
   and a small backlog of legitimately-paced frames arrived in a burst. Replaced with a token
   bucket that tolerates catch-up bursts but still rejects sustained abuse
   (`tests/unit/realtime/test_ingest.py`).
3. **The partial-transcript call blocked the ingest loop**, directly violating Task 1.4's own
   explicit requirement ("never let a partial pass block the audio ingest path"). It was
   `await`ed inline instead of fired as a background task; fixed, with an in-flight guard so
   overlapping partials can't pile up.
4. **`VoicePool.get()`'s first-time model load ran synchronously on the event loop**, so
   `asyncio.wait_for`'s 400ms deadline in `synthesize_with_deadline` couldn't even be checked
   — let alone fire — until the load finished. Moved the load inside the same
   `asyncio.to_thread` call as the synthesis itself.
   A related, smaller fix: `latency_events.id` was never populated on the batched insert path
   (the ORM's Python-side default doesn't apply to a Core `insert()`), which would have crashed
   every latency flush against a real database — caught immediately once real Postgres was in
   the loop, invisible to any test using a fake writer.

None of these four were guessable from reading the code; each one only showed up by actually
running the full stack and watching where a real turn got stuck. That is the whole argument
for doing this run at all rather than stopping at unit tests.

### What surprised me

- **Piper's cold start is slow enough to matter.** The very first synthesis call in a fresh
  process took ~5 seconds on this machine — over 12x the 400ms deadline — for a "faster than
  real-time" engine. Once warm (subsequent calls in the same process), it was consistently
  fast (`tts_first_chunk` ≈110ms in the clean run below). The deadline/fallback/holding-line
  design handled this exactly as intended: it degrades to a holding line and reports
  `degraded`, it doesn't hang or crash — but a cold first turn in a fresh process will
  genuinely show `degraded` in a real demo unless something pre-warms Piper with a throwaway
  synthesis call at startup, which is not currently done and would be a reasonable Day-11 fix.
- **One fully clean run, verified end-to-end, not just "it didn't crash":** transcript "The
  deployment finished about 10 minutes ago, and it looks good." (from
  `tests/fixtures/audio/clean_utterance_3s.wav`) → persona-stub reply, chunked into two
  sentences → real Piper audio for both → stage table (`endpoint_detect` 712ms,
  `asr_finalize` 933ms, `first_chunk_assemble` 152ms, `tts_first_chunk` 113ms, `e2e` 1830ms,
  over the 1400ms budget — expected; Day 11 is for tuning, not Phase 1) → session summary →
  both `turns` rows, the `turn_metrics` row, and all six `latency_events` rows confirmed
  present in the real database afterward → the upstream WAV (16kHz mono, correct duration) and
  the persona-reply WAV (24kHz mono, correct duration) both confirmed valid and playable → the
  recording confirmed present in real MinIO at `users/{user_id}/sessions/{session_id}.wav`.

### Decisions I made without being told, and why

Five more decision docs in `docs/decisions/`, continuing Phase 0's numbering:

- **`0003-realtime-db-access.md`** — realtime reads/writes Postgres through hand-mirrored
  SQLAlchemy Core tables, not api's ORM classes, to keep the two services genuinely independent.
- **`0004-worklet-resampling.md`** — one linear-interpolation resampler for both integer and
  non-integer sample-rate ratios, instead of two code paths; degenerates to exact decimation
  when the ratio is integral, so nothing is lost by not branching.
- **`0005-latency-stage-metadata.md`** — `stage()`'s metadata (e.g. ASR's RTF) goes to a
  structured log line, not the `latency_events` table, because that table's schema (Phase 0,
  frozen) has no metadata column and widening it is a real migration, not a Task 1.6a side effect.
- **`0006-session-end-reason-abandoned.md`** — the sweeper's finalize path closes with
  `end_reason="error"`, not the spec-text's `"user_abandoned"`, because the latter isn't in
  Phase 0's `SESSION_END_REASONS` CHECK constraint and writing it would crash the exact cleanup
  path that must never fail.
- **`0007-recording-upload-not-incremental.md`** — the recording uploads to S3/MinIO once, at
  finalize, not incrementally during the session as Task 1.2c's wording describes; the
  crash-safety property that wording is protecting is already fully satisfied by the local
  incremental disk write, which is unmodified.

### What I could not verify by running it

- **The AudioWorklet in a real browser.** `capture-processor.js` cannot run under vitest
  (no `AudioWorkletProcessor`/`registerProcessor` outside a real browser audio thread); its
  resampling/framing algorithm is verified by hand-derivation and the downstream framing logic
  it feeds is tested, but a real 5-minute browser capture session (Task 1.2's own acceptance
  criterion) has not been run. Same for `PersonaPlayback`'s `AudioContext` glue in
  `playback.ts` — the pure scheduling/backpressure/interrupt-guard logic is tested, the actual
  audio graph is not.
- **The interactive/live-microphone path of `scripts/cli.py`.** No microphone or speaker in
  this environment. `--replay` mode (the mode actually used for every real run above) and
  `record_from_microphone()`'s real-hardware path are both implemented; only the former is
  exercised here.
- **Stop-on-speech end to end.** The pure interrupt-guard logic (`InterruptGuard` in
  `playback.ts`, `handle_interrupt_window`/`do_interrupt` server-side) is unit-tested, but no
  live run actually interrupted a `speaking` turn mid-stream — that needs either a real second
  utterance mid-reply from a human, or a purpose-built integration test that wasn't built here.
- **A real 5-minute continuous session** (many turns back-to-back, resume after a genuine
  network drop). The single-turn run was thorough; multi-turn endurance and the resume path
  specifically were not exercised live.
- **The boundary-dataset precision number against real speech.** 0.57 precision is a real,
  measured number against the committed (synthetic) set — not fabricated — but it says "the
  cascade implements its own arithmetic correctly," not "this is what a real user will
  experience." See `data/boundaries/README.md`.

### Environment notes for future sessions

- Piper voices, the Silero VAD ONNX file, and both faster-whisper models (`base.en`,
  `tiny.en`) were already cached locally when this phase started. `ollama/qwen2.5:0.5b-
  instruct` (the configured `MODEL_ENDPOINTER`) was not pulled yet and was pulled during this
  phase (`ollama pull qwen2.5:0.5b-instruct`, ~400MB) — `qwen2.5:3b-instruct` (`MODEL_PERSONA_
  LOCAL`) was already present.
- A real `GROQ_API_KEY` and a running local Ollama were both available, which is why the
  persona-stream and semantic-endpointer tests could be genuinely live rather than skipped.
- Debugging the live run required stopping/restarting the `uvicorn` background process
  repeatedly and, twice, clearing stale rate-limit/session state the failed attempts left in
  Redis/Postgres (`ratelimit:sessions_hour:*`, sessions stuck in `status="created"`) — normal
  churn from iterating against real shared local infrastructure, not a product bug.

## 2026-08-22 — Phase 1 re-verification (before starting Phase 2)

Re-read `docs/01-SETUP-GUIDE`, `docs/phase-0-BUILD.md` and `docs/phase-1-BUILD.md` against the
actual repo state before starting Phase 2, per this session's own instruction to confirm Phase 1
is genuinely done first. Every claim in the Phase 0/1 notes above still held under a fresh
`make lint` + `make test` + a live CLI run — with two exceptions, both real, both fixed here:

- **`BackchannelCache` and `IdlePromptCache` were single-voice.** Phase 1 built and preloaded
  them for `settings.default_piper_voice` only; a session using any *other* seeded persona voice
  (`en_US-ryan-medium`, seeded content's actual default for most personas) got a cold, unwarmed
  cache for backchannel phrases and the idle nudge — silent under test (nothing asserts *which*
  voice a clip is cached for) but a real gap live. Both converted to `dict[voice_id, AudioClip]`,
  preloaded in `main.py`'s `lifespan()` for every entry in `settings.persona_voice_ids`, not just
  the default. `HoldingLine` stays single-clip on purpose — it's the fallback of last resort and
  is deliberately spoken in a fixed, always-available voice regardless of the session's persona.

No other gaps found. Phase 1 is confirmed complete; Phase 2 below is built on top of it, not
around it.

## 2026-08-22 — Phase 2: State machine, resume, persona, coach v0, latency, safety

Built all six tasks in `docs/phase-2-BUILD.md` in one session (the doc's own "one task per
session" rule explicitly waived for this session, per instruction), on top of the Phase 1
foundation above. As with Phase 0/1, acceptance criteria were run wherever real infrastructure
made that possible, against the real stack (`make up`'s Postgres/Redis/MinIO, real faster-
whisper, real Piper, real Groq, real local Ollama) — not just written. Eight real, non-obvious
bugs surfaced this way; see below.

### What exists now

- **The formal turn state machine** (2.1): `services/realtime/app/state_machine.py` rewritten to
  a data-driven transition table (10 server states, not 8 — `docs/decisions/0008` records four
  deliberate deviations from the literal spec table, including keeping `connecting` and adding
  `idle -> thinking` for the scripted opening line). `timeouts.py`'s poll-based watchdog
  (250ms tick, not per-state timers) supervises every state's timeout and drives every
  `degraded` transition in the spec's table, including the persona-model-429 -> switch-to-
  `MODEL_PERSONA_LOCAL`-for-the-remainder-of-session rule.
- **Reconnection, resume, coach enqueue** (2.2): a bounded 100-message resume-replay ring buffer
  (audio itself is deliberately never buffered — "stale audio in a live conversation is worse
  than silence"), incremental Opus-encoded checkpoint uploads during the session (not just at
  finalize — `docs/decisions/0009`; CBR, not VBR, after a measured compression-ratio bug, see
  below), and `score_turn`/`generate_report` ARQ enqueue with an in-memory retry list for a
  Redis outage that never blocks the turn path.
- **The persona agent** (2.3): three-layer prompts (`content/prompts/persona/{static,brief,
  dynamic}.v1.*`, static marked for prefix caching), difficulty as parameters rendered into
  behavioural instructions rather than three separate prompts (`persona/difficulty.py`),
  streaming generation with a post-generation safety filter and canned-deflection fallback
  (`persona/engine.py`, `persona/safety.py`), a planner-generated question plan that advances
  per-turn on vague-vs-strong answers (`persona/question_plan.py`), memory compaction every N
  turns, and the scripted opening line (`persona/opening.py`) delivered during warm-up before
  the user has said anything.
- **Coach v0** (2.5): the full `services/coach/` ARQ worker — deterministic metrics first
  (`deterministic/`), a prompted scorer with **exact-substring evidence verification** (a span
  that doesn't appear verbatim in the transcript is discarded and the score downgraded to low
  confidence, no exception), confidence gating (`not enough signal`, never a fabricated number),
  and a narrator that is handed already-fixed scores and evidence and is structurally forbidden
  from contradicting them. Runs entirely off the realtime service's process, queue-driven, per
  CLAUDE.md's hardest invariant.
- **Latency work** (2.4): partially complete — see its own section below, including a genuine
  root-cause fix and an honest account of what still doesn't hit budget on this hardware.
- **The safety suite** (2.6): `tests/safety/test_persona_safety_live.py` — 36 real, live-model
  test cases (no mocking; mocking the model call would fake away the exact thing under test)
  covering prompt injection (all six specified attacks, including the indirect "what would a 5/5
  answer look like" one), rubric fishing, distress detection in **both** directions, content-
  boundary refusal, and the post-generation filter — each parametrized against both
  `MODEL_PERSONA` (Groq) and `MODEL_PERSONA_LOCAL` (Ollama `qwen2.5:3b-instruct`) per the
  acceptance criteria. **All 36 passed** on a real run (`0:05:49`, both models). `make safety`
  runs it; `make test` deliberately excludes it (`-m "not safety"`) so routine dev runs stay
  fast and don't require live API credentials — `.github/workflows/ci.yml` has a dedicated
  `test-safety` job that fails loudly (not skips) if `GROQ_API_KEY` isn't configured, and installs
  Ollama to cover the local half.
  - Distress-exit handling turned out to be more than a prompt: the static prompt (v1.1.0) now
    requires the persona to open a genuine distress-exit reply with an exact, non-paraphrasable
    sentence ("I'm pausing this practice session.") specifically so the system can *detect* it
    reliably (`persona/safety.py::is_distress_exit_reply`) rather than guess from free-form text.
    That detector is exempted from the ordinary post-generation filter (a short reply adjacent in
    wording to its own prompt instruction is exactly what that filter could misfire on — the one
    reply that must never be swapped for a generic canned deflection). Detected only after the
    persona has *finished speaking* the line (never mid-sentence), it sets
    `SessionRuntime.distress_exit_pending`, which the state watchdog checks ahead of ordinary
    `idle` handling and routes to `_begin_closing(end_reason="distress_exit")` —
    `finalize_runtime` skips `score_turn`/`generate_report` enqueue entirely for that end_reason,
    and `session_closed.report_pending` is `false`. This was a real gap: before this session
    nothing detected a distress-exit reply or acted on it — CLAUDE.md's own acceptance criteria
    ("no scored report", "surfaces resources") had no code behind them yet. Actual resource
    *rendering* is a frontend concern — `apps/web` has no practice-room UI yet (confirmed: no
    session/practice-room files exist there) — so what's built here is the correct, complete
    server-side signal for that UI to consume once it exists, not the UI itself.

### The six real bugs this phase's live testing found (beyond the safety-suite gap above)

1. **`asyncio.CancelledError` isn't caught by `except Exception`** (Python 3.8+) in
   `timeouts.py::_cancel_turn_task` — caught by a unit test, not a live run, but only because a
   test was written to force the exact case; fixed with an explicit `except asyncio.CancelledError`.
2. **Opus VBR gave 6.5x compression, not the required ≥10x.** `options={"vbr": "off"}` (CBR)
   fixed it — verified live, 10.33x.
3. **`litellm.completion_cost()` doesn't accept `prompt_tokens`/`completion_tokens` kwargs** —
   a `TypeError` on every real cost calculation, in both `coach/app/cost.py` and
   `persona/engine.py`; fixed by switching to its `messages=`/`completion=` signature.
4. **A state-machine race**: the scripted opening line's own `idle -> thinking` transition and
   the frame-ingest loop start concurrently, so a client that starts talking immediately (the CLI
   replay harness does exactly this) could push `listening -> thinking` first and crash the
   warm-up task with `IllegalTransitionError`, silently (`asyncio` only logs "Task exception was
   never retrieved"). Fixed with `SessionRuntime.warm_up_complete`, gating VAD/state processing
   (not raw disk writes — those are untouched) in `_receive_messages` until the opener finishes.
5. **`runtime.voice_id` was hardcoded to the default Piper voice**, ignoring the session's actual
   seeded persona voice from the brief — found while wiring persona_context into `main.py`.
6. **An unhandled `RuntimeError` could crash a live connection outright.** `frame_pipeline.py`'s
   `_current_utterance()` assumed the state machine guarantees `runtime.current_utterance` is
   already set whenever state is `listening`/`endpointing` — true in the ordinary flow, but
   `asyncio.Task.cancel()` cannot actually interrupt a coroutine blocked inside
   `asyncio.to_thread` (a running OS thread doesn't stop just because the task wrapping it was
   cancelled; cancellation only lands once that thread returns control to the event loop). A slow
   ASR call inside `process_turn`, combined with `timeouts.py`'s `thinking`-timeout handler
   force-transitioning the session to `idle` while that call was still in flight, could leave
   `current_utterance` `None` while a later frame still saw `listening`/`endpointing` — and the
   old unconditional call turned that race into an uncaught exception that took the whole
   WebSocket connection down (surfaced live, gathering the Task 2.4 numbers below, as intermittent
   HTTP 403s on the *next* connection attempt — the crash left the session stuck in the in-process
   registry, silently eating a concurrency slot). Fixed: both branches now check the type before
   calling `_current_utterance()` and recover to `idle` (via `degraded` from `listening`, directly
   from `endpointing` — both already-legal transitions) instead of raising, matching CLAUDE.md
   §6's "degrades before it dies" everywhere else in this codebase.

### Task 2.4 — Latency: two real fixes, one honest gap

**The actual root cause of the opening-line TTS degradation wasn't a cold process — it was
ONNX Runtime's default thread pool.** Live testing kept showing the opening line miss its 400ms
`CHUNK_DEADLINE_MS` on *every* run, for both the primary and secondary voice, even after both
were pre-warmed at startup — ruling out Phase 1's "cold first call" theory outright. Direct
A/B benchmarking (same model, same sentence, 6 calls each, nothing else running) found
`onnxruntime.SessionOptions().intra_op_num_threads` defaulting to one thread per physical core
(10 on this machine) made every call 3-6x slower than `intra_op_num_threads=1` (916/839/726/
725/890/755ms vs. 162/110/95/281/335/328ms) — a small VITS model pays more in thread-pool
wake/synchronization overhead than it gains from that parallelism, and `piper.PiperVoice.load()`
doesn't expose `sess_options` as a parameter. `services/realtime/app/tts/piper.py::VoicePool`
now builds its own constrained `InferenceSession` (`intra_op_num_threads=1`,
`inter_op_num_threads=1`) instead of calling `PiperVoice.load()`. Full writeup, numbers, and why
Silero VAD/faster-whisper were *not* touched (the benchmark isolated this to Piper specifically)
in `docs/decisions/0011-piper-thread-pool-latency.md`. A second, smaller bug in the CLI harness
itself (`scripts/cli.py`) compounded this during testing: it declared a turn "done" on the first
`speaking -> idle` cycle, which — after Task 2.3f added the scripted opener — was the *opener's*
cycle, not the real reply's, so every replay run hung up mid-turn and reported "0 turn(s)." Fixed
by gating on `turn_finalized` having fired first, and by making the harness wait for the opener's
own cycle to finish before sending replay audio (matching what a real client would do — it
wouldn't start capturing mic audio before the UI shows it's the user's turn either), which also
fixed a silent transcript-truncation bug the race was causing (the first ~2s of a reply sent
during the opener window was written to disk but never reached VAD/ASR, since the same
`warm_up_complete` gate that ships bug #4 above also excludes it).

Backchannel masking (PA-10) is wired into `turn.py::process_turn` (`should_play_backchannel` —
unit-tested for all four constraints: rate-capped at ≤1/3 via `(used+1)/(turns_so_far+1)`, never
twice consecutively, never at hard difficulty, never before a wrap-up), plays the cached clip
the instant `thinking` is entered, before ASR even runs. It deliberately does **not** suppress
`e2e`/`tts_first_chunk` measurement for that turn — those still measure the real reply's timing,
not the backchannel's; letting a UX trick zero out the metric meant to catch real slowness would
violate CLAUDE.md §8/§10 even though the literal "first audible word" definition would technically
allow it.

Endpointing was re-run against the day-5 boundary set (`scripts/eval_endpointing.py`, 220 items)
and shows **no regression** — precision 0.573 vs. the day-5 baseline's 0.57, recall 1.000 both
times, as expected since no cascade threshold was touched this phase. Prefix caching is still
unmeasurable for Groq specifically (`docs/decisions/0010`, unchanged this phase). The first-chunk
word-cap tuning (8/12/16) was **not done** — see why below, the same reason it wouldn't have been
the thing deciding whether the gate is met.

**A precondition surfaced before the e2e number could even be gathered: `STATE_TIMEOUT_MS
[S.thinking]`'s literal spec value (5000ms) made turns fail outright on this hardware, not just
run slow.** A clean 55-turn batch (nothing else competing for the machine) at 5000ms completed
**0 of 55** turns — `asr_finalize` alone (`base.en`/int8 faster-whisper, this project's CPU-only
dev hardware) measured 2.5-8.2s across runs, so ASR by itself routinely consumed the entire
`thinking` budget before a reply — stub or real — had any chance to start. Full writeup and the
raw evidence in `docs/decisions/0008`'s Phase 2 addendum. Raised to 12000ms (margin above the
worst observed ASR call plus a persona TTFT on top); re-running the identical batch afterward
turned real turns on, at all, for the first time.

**`e2e` p50/p95, measured over real turns, `--persona-stub` and full path reported separately**
(queried directly from `latency_events`, `percentile_cont`, not summed per-stage — CLAUDE.md §8):

| | n | `asr_finalize` p50/p95 | `e2e` p50/p95 |
|---|---|---|---|
| `--persona-stub` (pipeline only) | 21 | 2499 / 3625 ms | 3822 / 5065 ms |
| full path (real persona) | 17 | 5157 / 12145 ms | 4484 / 5227 ms |

**Both miss the gate** (p50 ≤ 1100ms, p95 ≤ 1400ms) by a wide margin, and honestly: **n is 38,
not the ≥50 the acceptance criteria asks for.** Getting even this far took two full batch
attempts and a real architectural fix (the `thinking` timeout above) discovered only because the
first attempt returned zero usable turns instead of slow ones; reaching 50 cleanly needs either
a longer dedicated measurement window or a faster ASR path, and continuing to burn this session's
remaining time chasing the last ~12 turns wasn't a good trade against everything else still owed.
The number is real and honestly gathered, just short — not padded to look complete.

Given the ASR-dominated cost, this project's own escape hatch applies: "if the budget is not met
by end of day 11, descope reply richness before descoping speed... a terse fast persona beats an
eloquent slow one" — but the actual lever here isn't reply length (the stub row above, with *no*
persona model call at all, still misses the gate on `asr_finalize` alone), it's ASR model size or
hardware (GPU / a smaller Whisper variant), both of which are hardware/accuracy tradeoffs, not
something to change unilaterally. Flagged for a decision rather than decided here.

### Decisions I made without being told, and why

Three more decision docs, continuing the numbering:

- **`0008-phase-2-state-machine.md`** — four deliberate deviations from Task 2.1's literal
  transition table, plus (added live) the `S.endpointing` watchdog timeout raised from the
  spec's literal 200ms to 2000ms: the endpointing *cascade* (Task 1.3b) can legitimately hold
  `endpointing` for up to ~1.5s in its own worst case (900ms silence-accumulation + two 250-300ms
  extensions + an 80ms semantic-check timeout), and a literal 200ms watchdog was verified live to
  fire repeatedly during completely ordinary operation, not actual hangs.
- **`0009-incremental-upload-and-opus.md`** — checkpoint uploads during the session, not just at
  finalize; CBR Opus after the VBR compression-ratio bug above.
- **`0010-groq-cache-hit-unobservable.md`** — `model_calls.cached` is always `False` for Groq
  because the provider exposes no cache-hit signal to measure it from, not a claim prefix
  caching isn't happening server-side.
- **`0011-piper-thread-pool-latency.md`** — the ONNX Runtime thread-pool fix above.

### What I could not verify by running it

- **`e2e` p50/p95 over the full ≥50 real turns the acceptance criterion asks for** — 38 measured
  (21 stub, 17 real), real and honestly gathered, but short of 50. See above for why.
- **A resumed session after a genuine network drop, live.** `resume`'s logic is unit-tested
  (`test_resume_replay.py`) against a fake socket; a real disconnect/reconnect cycle against the
  live stack was not exercised this phase, same gap Phase 1 had for multi-turn endurance.
- **The coach report surface end-to-end against a session that actually finished multiple real
  turns.** The coach pipeline itself (`services/coach/`) has integration tests against real
  Postgres and was exercised live via `enqueue_generate_report`, but a full session — several
  real turns, then a real generated report read back — was not walked end-to-end live this phase
  the way Phase 1's single-turn run was; the closest live evidence is the coach integration test
  suite plus the individual live CLI turns run while debugging Task 2.3/2.4.
- **A real distress-exit session walked all the way through the WebSocket**, including the
  client actually receiving `session_closed` with `reason="distress_exit"` and
  `report_pending=false`. The *detection* (real Groq/Ollama calls, `is_distress_exit_reply`) and
  the *watchdog wiring* (`run_state_watchdog`'s new branch, unit-tested against a fake sink) are
  each independently verified; a real distress-utterance WAV was synthesized and replayed against
  the live stack four times specifically to close this gap, and every attempt hit the same wall:
  `litellm.RateLimitError` — this Groq API key's daily token quota (200,000 TPD) was at
  199,918/200,000 by the time this was attempted, entirely from this session's own extensive real-
  model testing earlier the same day (the 36-case safety suite alone, run against both models, is
  a meaningful share of it). Confirmed directly (a bare `litellm.acompletion` call against the
  same model, outside the app, returned the identical `rate_limit_exceeded`), so this is a hard
  external quota, not a bug — re-attempting needs either the daily reset or a different key.
- **`make safety`'s CI job specifically** (the GitHub Actions run, as opposed to the identical
  `pytest tests/safety` command run locally, which passed 36/36). Ollama install/serve/pull
  inside the CI runner and the `GROQ_API_KEY` secret being configured are both unverified from
  here — no push/CI access in this environment.
