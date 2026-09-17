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

## 2026-08-23 — Phase 0/1/2 re-verification (before starting Phase 3)

Per this session's own instruction to confirm Phases 0-2 before building Phase 3: re-ran
`make lint` (clean, all four checks — ruff, `mypy --strict` on realtime, mypy on api and coach,
eslint/tsc on web) and the full test suite from a cold state.

- **513/514 backend tests passed.** The one failure,
  `test_initial_prompt_biasing_recognizes_uncommon_term` (Task 1.4's vocabulary-biasing
  acceptance test), is a live faster-whisper call whose biased transcription came back
  "Spotbies" this run instead of the "Spotmies" the test asserts — closer than the *unbiased*
  "Sputbys" Phase 1 originally recorded, but not an exact match. This is real model
  non-determinism on a single hand-picked example, not a regression from anything touched this
  session (no ASR/VAD/persona code was changed in Phase 3). Flagged, not silently reasserted to
  a looser check.
- **30/30 web (vitest) tests passed** — `pnpm --filter @interactai/web run test` had been
  skipped by the pytest failure above in the combined `make test` run (Make aborts a recipe's
  remaining lines on a non-zero exit), so it was run directly.
- No other regressions found. Phases 0-2 are confirmed complete and unchanged; Phase 3 below is
  built on top of them.

## 2026-08-23 — Phase 3: The practice room and the report

Built all of `docs/phase-3-BUILD.md` in one session (its own "one task per session" rule
explicitly waived per instruction), on top of the confirmed Phase 0-2 foundation. This phase
touches every layer: new backend endpoints the report/replay surface needs but Phase 0-2 never
built, a from-scratch Next.js App Router frontend (`apps/web` had no `app/` directory at all
before this session — just the Phase 0-1 generated-schema tests and audio/protocol logic), and a
live end-to-end verification pass against the real running stack.

### What exists now

**Backend additions** (Task 3.3/3.4 needed real new surface, not just UI):

- **Recording metadata + waveform peaks** (`docs/decisions/0012`): `sessions.recording_key` /
  `.recording_format` / `.peaks`, written once by `services/realtime`'s `finalize_recording`
  (which already holds the decoded PCM in memory before Opus-encoding it — computing peaks
  there is free) and read by `services/api`'s new `GET /sessions/{id}/recording`, which mints a
  presigned S3/MinIO URL without ever touching the audio bytes itself (CLAUDE.md §2).
- **`GET /sessions/{id}/turns`** — every turn with its `turn_metrics` and `turn_scores` joined in
  Python (no FK exists between them and partitioned `turns`, docs/decisions/0002), gated scores
  (`score: null`) passed through exactly as stored, never re-derived.
- **`GET /sessions/{id}/scores`** — the session-level rollup, each row carrying the rubric's own
  anchor text joined in from `content_service`, plus a synthetic "Delivery" row for the
  deterministic criterion (name/anchors hardcoded once, `session_service.py`, since `delivery`
  isn't a real `rubric_criteria` row).
- **`POST /sessions/{id}/annotations`** (Task 3.4e/CS-15) — round auto-increments server-side per
  `(turn_id, annotator_id, criterion_key)`, so the uniqueness constraint can never be violated by
  a client that doesn't track its own round state (docs/decisions/0016). The model's own
  prediction is never in scope inside this endpoint or the frontend control that calls it.
- **`POST /sessions/{id}/retry`** (Task 3.4f) — copies the original session's entire frozen
  `brief`, overriding only `opening_strategy` (the persona turn immediately preceding the
  retried answer — `index < target_turn.index`, mirroring
  `services/coach/app/report/build.py::_find_preceding_question`) and `target_minutes` (fixed at
  5). No changes to `services/realtime`'s persona pipeline were needed — the retry session is an
  ordinary session whose scripted opener happens to ask a specific question
  (docs/decisions/0016).
- **`POST /sessions/{id}/replay-token` + realtime's `POST /synthesize`** (Task 3.4d,
  docs/decisions/0014) — on-demand persona-audio regeneration for report replay. A new,
  deliberately non-single-use token type (`typ: "replay"`, same `WS_TOKEN_SECRET`, 1-hour TTL)
  since the WS handshake token's single-use Redis burn would break the second play-this-line
  click of a replay session. Lives on `services/realtime`, never `services/api` (CLAUDE.md §2:
  api never touches audio; realtime already owns Piper and every warmed voice).
- **The OAuth callback fix** (docs/decisions/0013) — `GET /auth/{provider}/callback` now
  redirects to `{WEB_ORIGIN}/auth/callback#token=...&expires_in=...` instead of returning JSON
  directly. The original Phase 0 handler could not have worked with any browser-based frontend:
  the provider's own redirect lands the browser here as a top-level navigation, and a JSON
  response would just strand the user on a bare API page with no route back into the app. Found
  and fixed while building the actual sign-in button, not before — Phase 0's own acceptance
  criteria explicitly scoped the live OAuth round trip out as needing "a human + a real browser."
- **`GET /me` now returns `practice_minutes_this_week`** (Task 3.1's sidebar meter) — calendar
  week starting Monday 00:00 UTC, summed from real `sessions.duration_ms`.
- A new migration (`c3d4e5f6a7b8`) for all of the above; `services/realtime/app/db/tables.py`'s
  Core mirror of `sessions` updated to match (docs/decisions/0002's pattern).

**Frontend** (`apps/web`, built from nothing — Next.js 15 / React 19 / Tailwind v4 / Zustand /
TanStack Query / wavesurfer.js / cmdk, added to what was previously a schema-tests-only
workspace):

- **Design tokens** (Task 3.1): dark-first with a genuine light mode
  (`app/globals.css` — three colour-token blocks, not an inversion filter), exactly six font
  sizes and two weights enforced by resetting Tailwind v4's `--font-size-*`/`--font-weight-*`
  namespaces and redefining only those, and a real CI-style check
  (`apps/web/scripts/check-design-tokens.mjs`, chained into `pnpm run lint`) that greps for raw
  hex colours in any component and confirms the four reserved score-colour tokens are referenced
  nowhere outside `components/score/` — the one directory that consumes them, via
  `components/score/score-color.ts` rather than any other file spelling out the token names
  directly.
- **App shell** (Task 3.1): collapsible sidebar with the practice-minutes meter, top bar with
  breadcrumb + "Start practice" + user menu, a `cmdk`-based command palette (⌘K) with real
  scenario/session search and the three specified verbs, a toast region. Applied to every
  authenticated route except the practice room via a `(shell)` route group; the practice room
  sits in a sibling `(bare)` group with no shared layout at all.
- **The practice room** (Task 3.2, `components/practice/practice-room.tsx`) — the one client
  boundary on its route, exactly as specified. `lib/realtime/connection.ts` (a framework-free WS
  state machine, testable by injecting a fake socket — 9 unit tests covering hello-vs-resume,
  session_busy detection distinct from token-reuse despite sharing close code 4409, exponential
  reconnect backoff, and clean-vs-abnormal close handling) drives `stores/practice-store.ts`.
  `lib/realtime/audio-text-correlator.ts` solves a real protocol subtlety: the wire format sends
  a chunk's audio-meta, binary frame and text as three separate messages with no shared id,
  correlated only by send order (5 unit tests). The mic level meter and the speaking ring's
  amplitude both bypass React state entirely, writing straight to a CSS custom property from a
  worklet callback / `requestAnimationFrame` loop respectively (`lib/audio/playback.ts` gained a
  real `AnalyserNode` for this — previously unused since Phase 1 built no consumer for it).
  `useAudioCapture` (`hooks/use-audio-capture.ts`) handles all three device edge cases: denial
  (browser-specific recovery instructions, `lib/browser-detect.ts`), mid-session revocation (a
  new `onTrackEnded` hook added to `lib/audio/capture.ts`'s `createMicCapture`, since it didn't
  expose the raw track before), and `devicechange` re-acquisition. The pre-flight check (AU-09)
  reuses the real pipeline rather than a synthetic mode that doesn't exist server-side
  (docs/decisions/0017) — the scripted opening line already playing is the speaker proof, the
  user's first live partial transcript is the capture/ASR proof.
- **The report** (Tasks 3.3/3.4, `components/report/*`) — server-computed peaks feed wavesurfer.js
  directly (no client-side audio decode), turn-boundary regions and highlight/lowlight markers
  sync independently of the waveform's own create/destroy lifecycle (a real bug caught and fixed
  during this session: regions were originally baked in at instance-creation time, so a `turns`
  query resolving *after* the `recording` query would silently ship a waveform with no regions at
  all forever — see `hooks/use-report-waveform.ts`'s two-effect split). One `playheadMs` in
  `stores/player-store.ts` drives the transcript's auto-scroll, the score panel's active
  criterion, and the verdict block's evidence links — `lib/report/derive-current-turn.ts`,
  `lib/report/build-transcript-segments.ts` and `lib/report/map-char-offset-to-ms.ts` are the
  pure, unit-tested derivations underneath (evidence-span-to-seek-time in particular walks
  `word_timings` to locate each word's real position in `turns.text`, correctly resolving
  repeated words to their actual occurrence — 6 unit tests). The annotation control never
  receives the model's prediction as a prop at all, not just visually hidden. Retry-one-question
  is a button on every user turn. Deep-linking (`?turn=&t=&criterion=`) restores once on mount
  and re-syncs on a 300ms debounce thereafter. wavesurfer's `<canvas>` rendering can't resolve
  CSS `var()`, so every waveform colour is resolved to a concrete value via
  `lib/theme/resolve-css-var.ts` before being handed to it — region colours, being real DOM
  elements underneath, don't have this problem, verified by reading wavesurfer's own regions
  plugin source rather than assumed.
- **Auth** (docs/decisions/0015): access token in memory only (never `localStorage`), the
  existing Phase 0 httpOnly refresh cookie exchanged via `POST /auth/refresh` on boot and once
  on any 401. `/app/*` pages are thin Server Components; all authenticated data fetching happens
  client-side via TanStack Query — a deliberate, recorded deviation from the phase doc's literal
  "Server Component fetches session/scenario/persona" sketch, since the practice room needs
  browser-only APIs regardless and this architecture has no SSR-readable access token to give a
  Server Component in the first place.

### Real bugs this session's own live testing found

1. **The OAuth callback couldn't work at all** (see above) — not a live-run discovery in the
   usual sense (no OAuth app credentials with a real callback were exercised here either), but
   found the moment the sign-in button's actual flow was traced end-to-end while building it.
2. **The waveform region-sync bug** (see above) — caught by re-reading the hook's own dependency
   array against the real shape of three independent, differently-timed TanStack Query fetches,
   not by a failing test (there was no test for this interaction). Fixed before it shipped.
3. **Two duplicate `uvicorn` processes were already bound to ports 8000/8080** when live
   verification started this session — leftover from an earlier session's live-testing (process
   creation timestamps ~5 hours before this session started, command lines matching an older
   invocation style), serving stale pre-Phase-3 code. `GET /me` silently missing the new
   `practice_minutes_this_week` field and the new `/turns`/`/scores`/`/recording`/`/replay-token`
   routes all 404ing were the tell; `netstat` + process command-line inspection confirmed which
   PID was which before stopping the stale ones. A reminder that this environment's background
   processes persist across sessions and aren't reset automatically.
4. **A dangling, unreachable git commit** (`0a667c0`, message "version012") was found in the
   repository's object database — not on any branch, not part of `git log`, but a genuine, very
   recent (same-day) full snapshot of the repo close to its current state. It was used once,
   surgically, to recover the original `services/api/app/core/s3.py` after this session
   accidentally clobbered it with `Write` instead of reading-then-editing (a real process error,
   caught immediately via `mypy` failing on a now-missing `delete_prefix` import that
   `services/api/app/services/user_service.py` depends on for account deletion). Worth knowing
   this commit exists — it may be an automatic checkpoint from tooling outside this
   conversation's control, not something this session created.

### What was verified by actually running it

- **The full backend build**: `make lint` (ruff, `mypy --strict` on realtime, mypy on api and
  coach, eslint/tsc/design-token-check on web) clean; `tests/integration/` (34 tests, real
  Postgres/Redis via testcontainers, including a new 13-test file exercising every new endpoint
  above) all passing; the realtime session-lifecycle unit test files (145 tests) unaffected by
  the `close_session`/`finalize_recording` signature changes.
- **The full frontend build**: `pnpm run typecheck`/`lint`/`test` clean (84 vitest tests across
  14 files); a real `next build` production build succeeds, including the dynamic
  `/app/practice/[sessionId]` and `/app/sessions/[id]` routes.
- **A live, multi-service smoke test against the real stack** (`make up`'s Postgres/Redis/MinIO,
  real `uvicorn` processes for api and realtime, migrations + `make seed` applied): created a
  real user, minted a real access token, created a real session, and called every new endpoint
  live — `GET /me` (confirmed the new field), `GET /sessions/{id}/recording` (confirmed the
  correct all-null shape for a session with no recording), `GET /sessions/{id}/turns` and
  `/scores` (confirmed empty-array shape), `POST /sessions/{id}/replay-token`, and
  `POST /sessions/{id}/ws-token`. Most notably, **`POST /synthesize` was called for real** with a
  real replay token against the real running realtime process: it returned a genuine, valid WAV
  (mono, 24kHz, 3.36s, verified by actually parsing the file with Python's `wave` module) for a
  sentence of text, with the correct `Access-Control-Allow-Origin: http://localhost:3000` header
  present — the entire Task 3.4d pipeline (mint token -> validate token -> real Piper synthesis
  -> CORS-correct response) confirmed end-to-end, not just unit-tested. `next start` was also run
  and its `/`, `/auth/callback` and `/app` routes confirmed to return real, correctly-hydrated
  HTML (including the `next/font` Inter/JetBrains Mono variable classes) via `curl`. Test data
  and the extra background processes were cleaned up afterward.

### What I could not verify by running it

- **Any real browser interaction at all.** No browser, display, microphone, or speakers exist in
  this environment. Every piece of DOM/Web-Audio-dependent logic that *can* be unit-tested
  without a browser (worklet meter math, the WS state machine, the audio/text correlator, the
  transcript segment builder, the char-offset-to-ms mapper, the player/practice Zustand stores)
  has real tests and they pass; the pieces that fundamentally cannot be — `getUserMedia` actually
  prompting and streaming, the `AudioWorkletNode` capture pipeline as a whole, wavesurfer.js
  actually painting a canvas and responding to a real click/drag, the command palette's and
  dialogs' real keyboard focus behavior, any visual/dark-vs-light rendering check — are
  code-reviewed and built to spec but not run in a browser this session. Same category of gap
  Phase 1 recorded for the AudioWorklet and Phase 2 recorded for the browser side of the practice
  room's precursors.
- **A full 10-minute live practice-room session** (Task 3.2's own acceptance criterion), a real
  Wi-Fi-drop-and-reconnect, and a real screen-reader pass over the ARIA live regions — all built
  to the spec's exact wording (`state_change.client_state` mapped directly, never re-derived;
  `role="status" aria-live="polite"` on the turn indicator; reduced-motion checked via
  `matchMedia` before any `requestAnimationFrame` loop starts) but not run live.
- **The 60-turn transcript's actual frame rate.** `content-visibility: auto` was chosen
  deliberately over a windowing library (docs/decisions/0017) but never measured against a real
  60-turn session in a real browser.
- **`GET /sessions/{id}/report`'s progressive-rendering polling against a real coach run** —
  `useSessionReport`'s `refetchInterval` logic was code-reviewed, not run against an actual
  `generate_report` job completing while the report page was open (that path is Phase 2's own
  already-tested `services/coach` pipeline; connecting it live to *this* page's polling wasn't
  exercised this session).
- **CI** — no push/CI access in this environment, same standing gap as every previous phase.

### Follow-up quick-verification pass (same day)

Requested as a second pass to confirm everything above and finish anything left incomplete.
Nothing was left incomplete; one further latent bug surfaced and was fixed:

- **The `.gitignore` fix above had an immediate, visible consequence**: `ruff check .` discovers
  files by walking the tree and skipping gitignored paths by default — so `services/api/app/
  models/*.py` had never actually been linted by `make lint` before, the whole time it was
  invisible to git. The instant it became visible, `ruff` surfaced five real (if minor)
  pre-existing style violations there — four over-length lines and one redundant quoted forward
  reference — from as far back as Phase 0. All five fixed; `make lint` is clean again, now
  genuinely covering every file it always should have. (`mypy` was unaffected either way — it's
  invoked with an explicit path, not gitignore-aware directory discovery, so it was already
  checking these files every time.)
- Re-ran the full non-safety backend suite from a warm environment: **532 passed, 0 failed**
  (up from 513/514 — the 18 new tests from this session's own additions), including the
  previously-flaky whisper vocabulary-biasing test passing clean this time. Full `make lint`,
  all 34 integration tests, all 84 frontend tests, and a fresh `next build` all re-confirmed
  green. `git add --dry-run services/api/app/models/` confirmed only the ten real `.py` files
  stage — no `__pycache__` leakage through the newly-un-ignored path.

## 2026-08-23 — Phase 3 re-verification (before starting Phase 4)

Per this session's own instruction to confirm `01-SETUP-GUIDE`, Phase 0-3 are genuinely done
before starting Phase 4, from a **fresh session with a cold environment** (a new git worktree
state, Docker Desktop not yet running, no leftover `uvicorn`/`arq` processes) — a stronger check
than re-running in a warm environment, since it can't silently benefit from state a prior session
left behind.

- **`git status` was clean and `git log` matched the previous session's final commit exactly**
  (`47870ca "version 0123"`) — no uncommitted work, no untracked non-ignored files anywhere in
  the tree. Nothing from Phase 3 was left undocumented or unstaged.
- **Full `make lint` equivalent, run as its five underlying commands directly, all clean**: `ruff
  check .`, `mypy --strict services/realtime/app` (53 files), `mypy services/api/app` (41 files),
  `mypy services/coach/app` (25 files), `pnpm --filter @interactai/web run lint` (eslint +
  `scripts/check-design-tokens.mjs` — "no raw hex colours, score colours properly scoped"),
  `pnpm --filter @interactai/web run typecheck` (`tsc --noEmit`).
- **Backend tests**: first run (testcontainers Postgres/Redis already warm from a stale prior
  session, but the Compose stack — including MinIO — not yet started via `make up`) showed **2
  failures**, both `TestDeleteMe` cases in `tests/integration/test_auth_and_sessions.py`, both
  `botocore.exceptions.EndpointConnectionError` against `localhost:9000` — not a code regression,
  just MinIO not running yet in this fresh session. `make up` (brings up Postgres/Redis/MinIO
  with real healthchecks) then re-running exactly those two tests: **both pass.** Net result
  **527 passed, 5 skipped, 36 deselected (the live safety suite)** — arithmetically identical to
  the previous session's "532 passed, 0 failed" (527 + 5 = 532; the 5 skips are legitimate,
  environment-conditional `skipif`s — Piper voices/Silero model/audio fixtures/Ollama/MinIO
  presence checks in `tests/unit/realtime/`, not new gaps). Phase 3's own claim holds exactly.
- **Frontend tests**: `pnpm --filter @interactai/web run test` — **84/84 passed**, 14 files,
  matching Phase 3's number exactly.
- No new undocumented work found, and no regressions. **Phase 0-3 are confirmed complete and
  unchanged.** The only thing this pass added beyond re-confirmation: Docker Desktop was not
  running at all at session start (not just "stale containers" — the daemon itself was down) and
  had to be launched fresh, which is itself a useful data point — this environment's Docker does
  not survive a full session boundary the way `uvicorn`/Postgres/Redis processes apparently did
  in Phase 3's own session (its point 3 above, about stale `uvicorn` processes). Phase 4 below is
  built on top of this confirmed foundation.

## 2026-08-23 — Phase 4: Shell, onboarding and real users

Built all of `docs/phase-4-BUILD.md`'s coding tasks (4.1-4.5) in one session (its own "one task
per session" rule explicitly waived per instruction), on top of the confirmed Phase 0-3
foundation. Task 4.6 (the recruited-session day itself) is explicitly "not a coding task" and
needs 10-15 real human participants with real microphones — see its own section at the end of
this entry for exactly what that means here.

### What exists now

**Backend additions** — a new migration (`d4e5f6a7b8c9`), five new/extended services, and
roughly twenty new endpoints, all on `/me/*`, `/sessions`, and `/personas/*`:

- **Onboarding + audio + privacy + models profile fields** (Task 4.3/4.4): `profiles` gained
  `goal`, `experience_level`, `focus_areas`, `captions_default`, `speaking_rate`,
  `noise_suppression`, `echo_cancellation`; `users` gained `training_consent`,
  `audio_retention_days`, `prefer_local_models`, `onboarded_at`. `PATCH /me/profile` is the one
  endpoint every onboarding step and every Settings > Profile edit writes through — Task 4.3's
  "abandoning and returning resumes at the right step" needs no separate state table, since the
  current step is derived purely from which fields `GET /me` already shows as filled in.
- **`POST /me/onboarding/complete`** — idempotent, sets `onboarded_at` once.
- **`GET`/`PATCH /me/privacy`** (AS-03/AS-04) — `training_consent` and `audio_retention_days`.
  Turning `training_consent` off cascades immediately
  (`user_service.py::revoke_training_consent`): every one of the user's own turns (not the
  persona's — a persona turn is synthetic, not the user's contribution) from a session whose own
  `Consent` row recorded `training_consent=true` gets `training_excluded=true`, permanently — a
  later re-grant only changes the default *new* sessions get, it never un-excludes a past
  revocation. Logged via structlog, per Task 4.5a's own instruction.
- **`consents` table + a `Consent` row for every session** (Task 4.5a), not only the
  recruited-session flow's screen: `recording_consent` defaults true (capture is how the product
  works at all), `training_consent` defaults to the account's own `users.training_consent` unless
  the caller — `POST /sessions`'s new `recording_consent`/`training_consent` fields — overrides
  it explicitly. `retry_of_session` sessions inherit the original session's own consent decision
  rather than re-defaulting.
- **`provider_credentials` table + BYOK** (Task 4.4): `core/crypto.py` (Fernet, keyed off
  `APP_SECRET` — the same secret already used as the refresh-token pepper) encrypts the key at
  rest; no response body ever contains it, only `has_key`/`last_test_status`. `POST /me/providers/
  {provider}/test` makes a real, minimal call against Groq's own API (not a format check) —
  verified live against the real provider, both branches: a syntactically-plausible fake key gets
  a genuine 401 back and reports failure, and the "no key saved yet" case reports failure with a
  clear message.
- **`turns.text_scrubbed` + `services/coach/app/privacy/scrub.py`** (Task 4.5b/AS-06): spaCy
  `en_core_web_sm` NER for PERSON/ORG/GPE plus regex for email/phone/salary figures, replaced with
  pseudonyms stable *within a session* (`PseudonymTracker`, keyed by label + lowercased span
  text) — wired into `generate_report` so every turn's scrubbed text is written once a report
  actually generates, alongside the unscrubbed `text` every existing report/replay/evidence-span
  surface keeps reading unchanged. Coach's own hand-mirrored `turns` Core table
  (`services/coach/app/db/tables.py`) was missing `updated_at` entirely — a real, immediate bug
  the first live-ish test run of this caught (`sqlalchemy.exc.CompileError: Unconsumed column
  names: updated_at`), fixed by adding the column to the mirror.
- **`scripts/expire_recordings.py` + `services/api/app/services/retention.py`** (Task 4.4's
  "Retention setting is honoured by the expiry job"): a pure `is_recording_expired()` decision
  function (7 unit tests, including the exact-boundary case and the `retention_days=0` "delete
  immediately after scoring" case depending on report status rather than elapsed time at all),
  wrapped by a thin script that deletes the S3 object and nulls `recording_key`/`.recording_format
  `/`.peaks` — dry-run-tested against the real dev stack.
- **`GET /me/dashboard`** (Task 4.1) — the five-rule recommendation ladder (incomplete session ->
  weakest-trending criterion's family -> never-attempted family -> next difficulty tier -> the
  onboarding goal's family), a progress strip (sessions/minutes this week, confidence-weighted
  overall score + delta vs. the previous session, weakest criterion by trend), the last five
  sessions, and an attention panel showing **at most one** of an unread report / a scenario
  attempted 3+ times without improving / a declining criterion — verified live end-to-end
  (the "never-attempted family" branch actually fired against real seeded content).
- **`GET /me/progress?family=`** (Task 4.4) — defaults to the user's most-practised family, never
  "all"; per-criterion trend (last-3-points, newest minus oldest — deliberately *not* weighted by
  absolute level, so "a criterion at 5 and declining" beats "one at 4 and stable" exactly as the
  phase doc's own worked example asks, and a fixture-data test proves it); weekly practice volume;
  family coverage; personal bests.
- **`GET /me/scenario-progress`** (Task 4.2's "the user's own best score if attempted") and its
  richer sibling used by the scenario detail page — `session_service.get_scenario_attempts`
  returns attempt count, best score, and up to 10 recent attempts with links to their reports.
- **`POST /personas/{id}/voice-preview-token` + realtime's `POST /synthesize-preview`** (Task
  4.2's "voice preview... without starting a session") — a new token type (`typ: "voice_preview"`,
  same `WS_TOKEN_SECRET`, scoped to a `voice_id` not a session, not single-use), and a new
  realtime endpoint that always synthesizes one fixed, server-side sentence (never client-
  supplied text — otherwise the endpoint would be an open TTS service once someone has a token).
  Verified live: a real token round-tripped through `validate_voice_preview_token`, and the real
  `/synthesize-preview` call returned a genuine, parseable 24kHz mono WAV (4.17s, Python's `wave`
  module).
- **`GET /me/export`** (Task 4.4) — a JSON archive of profile, sessions, transcripts and scores;
  deliberately excludes any `encrypted_api_key` and raw audio (regenerable/re-fetchable, not
  duplicated into an export).
- **`sessions.report_viewed_at`** — a new column, set once as a side effect of `GET /sessions/
  {id}/report` actually returning a ready report, purely so the dashboard's "unread report" signal
  has something real to read (it didn't exist before this phase).

**Frontend additions** (`apps/web`) — the practice-library page from Phase 3 split into a real
dashboard (`/app`) and a real scenario library (`/app/scenarios`), plus five wholly new routes:

- **Dashboard** (`/app`, Task 4.1) — primary action block (the recommendation, with its required
  human-readable reason), a four-figure progress strip, an attention panel, last five sessions,
  and a genuine empty state for a brand-new user. Redirects a never-onboarded user to
  `/onboarding` (a user whose `onboarded_at` is still null, not a session-history check — a user
  who *has* onboarded but has zero sessions yet still sees the dashboard's own empty state).
- **Scenario library** (`/app/scenarios`, Task 4.2) — family/difficulty/duration/tag filters, all
  URL-encoded and restorable on reload; each card shows the user's own best score if attempted;
  a "Custom scenario" card links to `/app/scenarios/custom`, an honest "coming soon" page per the
  phase doc's own instruction not to build the authoring flow.
- **Scenario detail** (`/app/scenarios/[id]`) — brief, persona (with a working voice-preview
  button), the rubric's criteria with every anchor descriptor behind a disclosure, previous
  attempts linking to their reports, and a launch panel.
- **`/onboarding`** (Task 4.3) — a new top-level authenticated route (outside both the shell and
  the practice room's own route groups), 4 steps derived from `GET /me`'s own state (no separate
  onboarding-state table to drift out of sync): goal (3 cards), profile (target role/experience/
  optional resume, with the privacy consequence stated inline, not behind a link), then a real
  5-minute session is created for the goal's scenario family and the browser is sent straight into
  `/app/practice/{id}?onboarding=1` — the *existing* pre-flight overlay (Task 3.2 AU-09, reused
  rather than rebuilt) **is** the audio check, and passing it simply continues into what the phase
  doc calls "step 4." A brand-new, additive, optional `micDeniedExit` prop on `PracticeRoom`/
  `MicPermissionError` (every other caller omits it, unchanged) gives Task 4.3's "skip for now"
  edge case a real exit back to `/app` without touching the practice room's core behaviour.
- **`/app/progress`** (Task 4.4) — family filter (tabs), per-criterion trend sparklines paired
  with the latest `ScoreBadge`, a weekly-volume bar chart, family-coverage chips, and personal
  bests linking to their reports.
- **`/app/settings/*`** (Task 4.4) — a tab layout over five sections: **Profile** (extended with
  goal/experience/focus areas, a prominent inline resume-delete control), **Audio** (device
  enumeration + selection, echo-cancellation/noise-suppression toggles, speaking-rate slider,
  captions-default toggle, and a new self-contained, local-only `AudioCheckPanel` — a
  "re-runnable audio check" that reuses the exact same `useAudioCapture` hook and `MicLevelMeter`
  the practice room uses, plus a Web-Audio oscillator test tone with a "did you hear that?"
  confirmation, all without needing a live session), **Privacy** (training consent, retention
  window, JSON export, delete-account with a type-DELETE-to-confirm guard), **Models** (BYOK save/
  test/remove, prefer-local-models toggle), **Notifications** (the in-app toast is real and shown
  as "Always on"; the two email channels the phase doc asks for are honestly disabled with a
  label rather than a toggle nothing would act on — no email/SMTP provider has ever been
  provisioned in this project, see `docs/decisions/0018`).
- **Consent screen** (`components/dashboard/consent-screen.tsx`, Task 4.5a) — two independent
  checkboxes (recording, training), neither pre-checked, wired into `StartSessionDialog` behind a
  new "this is a recruited/research session" toggle: checking it shows the consent screen before
  `POST /sessions` fires at all, and the two explicit answers are threaded straight into the
  session-create call. An ordinary session skips this entirely and falls back to the account's
  own Settings > Privacy default, verified live (both branches, via direct DB inspection of the
  resulting `consents` row).
- **`captions_default` now actually reaches the practice room**: a real, if minor, gap was found
  and fixed while wiring the new Settings > Audio page — Phase 3's `captionsEnabled` was
  browser-localStorage-only with no path from the new server-persisted `profiles.
  captions_default` at all. `stores/shell-store.ts::seedCaptionsDefault` (3 new unit tests) now
  seeds the local value from the server default the first time this browser has never expressed a
  preference, and never overrides an explicit local choice on any later visit.
- **Input-device selection and echo-cancellation/noise-suppression now actually reach live mic
  capture**: `lib/audio/capture.ts::createMicCapture` gained an optional, additive `constraints`
  parameter (deviceId/echoCancellation/noiseSuppression), forwarded from `useAudioCapture`'s own
  new optional option — every existing caller that doesn't pass it gets exactly the old hardcoded
  behaviour. `speaking_rate` and the saved *output* device are persisted and round-tripped but
  deliberately not wired into live TTS synthesis / `setSinkId` — see `docs/decisions/0018` for
  why (both touch latency-critical or already-tuned paths this phase judged not worth the risk
  for a settings preference).

### Real bugs this session's own testing found

1. **`tests/integration/test_db_schema.py`'s raw-SQL bulk-insert fixture broke** the instant
   `turns.training_excluded` went `NOT NULL` without a permanent server default (matching this
   project's own established convention of dropping the server default after backfill and relying
   on the ORM's Python-side default — which a raw `INSERT INTO turns (...)` naturally bypasses).
   Not a design flaw in the migration; a pre-existing fragility in a synthetic stress-test's own
   hardcoded column list that any future `NOT NULL` column addition would have hit the same way.
   Fixed by adding the new column to that one fixture's INSERT statement.
2. **`services/coach/app/db/tables.py`'s hand-mirrored `turns` table was missing `updated_at`
   entirely** — invisible until this phase's `set_turns_scrubbed_text` became the first thing
   coach ever *wrote* to `turns` (every prior use was read-only), surfaced immediately as a
   `CompileError` in `tests/integration/test_coach_pipeline.py`, not a live run. Fixed by adding
   the column to the mirror, matching every other coach table's own convention.
3. **The salary regex silently ate a trailing space** ("$145,000 last year" -> "[SALARY_1]last
   year", words mashed together) — caught by a manual smoke test of the scrubber before the
   formal test suite was even written, not by the tests themselves (which were written after,
   deliberately covering this exact case once found). Fixed by scoping the optional `k`-suffix
   match so it can't independently consume a bystander space.
4. **The salary regex missed bare two-digit `k`-shorthand ("165k" with no `a year`/`dollars`
   suffix at all)** — caught by this session's own test suite (`test_catches_a_shorthand_k_
   salary_figure`), not a live run. A separate, deliberately bounded (`\d{2,3}[kK]`) alternative
   added, trading a modest false-positive risk (e.g. "500k users") for catching the much more
   common salary-shorthand phrasing an interview transcript actually contains.

### What was verified by actually running it

- **The full backend build**: `ruff check .` and `mypy --strict`/`mypy` on all three services
  clean; **574/574 relevant backend tests pass** across two full runs (`uv run pytest` directly,
  then again via `make test`). Two tests failed, each exactly once, on different runs, both in
  code this phase never touched: `test_process_window_runs_under_3ms` (VAD timing under
  concurrent system load — this environment was also running Docker/other test processes at the
  time) and `test_initial_prompt_biasing_recognizes_uncommon_term` (the same faster-whisper
  vocabulary-biasing non-determinism `docs/PROGRESS.md`'s own Phase 0-2 re-verification section
  already recorded as flaky on this exact fixture). Both were re-run in isolation immediately
  after and passed cleanly — confirmed pre-existing, hardware/model-non-determinism flakes, not
  Phase 4 regressions — plus 1 environment-conditional skip and the 36 deselected live
  safety-suite cases (unrelated to this phase, not re-run since no persona/safety code changed).
  `make test` itself aborts before running the frontend suite the moment `pytest` returns
  non-zero (documented Make behaviour, not a bug) — the frontend suite was verified separately,
  repeatedly, via direct `pnpm run test` calls, always 91/91.
- **The full frontend build**: `pnpm run typecheck`/`lint`/`test` clean — **91/91 vitest tests**
  across 16 files (7 new: the scrubber isn't frontend, but `device-prefs.test.ts` and
  `shell-store.test.ts` are, both new this phase); a real `next build` production build succeeds
  across all 17 routes, including the 5 new dynamic/static Phase 4 routes.
- **A live, multi-service smoke test against the real running stack** (`make up`, real `uvicorn`
  for both api and realtime, migrations at head): **18 consecutive live calls against every new
  endpoint, all succeeded** — `GET /me`, `PATCH /me/profile`, `GET`/`PATCH /me/privacy`, `GET /me/
  models`, `GET /me/dashboard` (confirmed the "never-attempted family" recommendation actually
  fired against real seeded content), `GET /me/progress`, `GET /me/scenario-progress`, `GET /me/
  export`, the full BYOK round trip (`PUT`/`GET`/`POST .../test`/`DELETE` on `/me/providers/groq`
  — the connection test against a fake key returned a real 401-derived failure from the live
  Groq API, not a stub), `POST /me/onboarding/complete`, `POST /personas/{id}/voice-preview-
  token` followed by a real `POST /synthesize-preview` against realtime that returned a genuine,
  parseable 24kHz mono WAV, and `POST /sessions` with explicit `recording_consent`/
  `training_consent` — confirmed by direct SQL query afterward that the resulting `consents` row
  had exactly the values sent (`True`/`False`), not the account defaults. The test user was then
  deleted through the real `DELETE /me` endpoint and a follow-up query confirmed **zero** residual
  `users`/`sessions`/`consents` rows — the cascade-delete path re-verified, not just assumed
  unaffected by the new tables hanging off it.
- **`scripts/expire_recordings.py --dry-run`** run against the real dev stack — exits cleanly,
  reports zero expirable recordings (correct: no session in the dev DB is old enough).
- **19 new/updated integration tests** (`tests/integration/test_phase4_dashboard_privacy_byok.py`)
  covering onboarding idempotency, the privacy-revocation cascade (including that a persona's own
  turns are *not* excluded and that re-granting consent doesn't retroactively un-exclude a past
  revocation), BYOK credential CRUD and the never-leaks-the-raw-key property, consent-on-create
  for both the default and explicit-override paths, the dashboard recommendation ladder, the
  attention panel's "at most one, absent when nothing qualifies" property, the trend-not-absolute
  weakest-dimension fixture case Task 4.4 explicitly asks for, family-defaults-to-most-practised,
  scenario best-score-across-attempts, and export's never-leaks-the-key property — plus 2 for the
  new voice-preview-token endpoint. **15 new PII-scrubber unit tests** and **7 new retention-
  decision unit tests**, all passing.

### What I could not verify by running it

- **Task 4.3's own acceptance criterion, verbatim: "A stranger, unaided, goes from signup to
  speaking in a session in under five minutes (test this with an actual person, not by clicking
  through yourself)."** No person, browser, or microphone exists in this environment — the same
  standing gap every previous phase has recorded for anything requiring a real human at a real
  keyboard. The onboarding flow was traced logically and every piece that can be unit-tested
  without a browser (the step-derivation logic, the recommendation ladder, the consent screen's
  own component logic) has real tests; the actual five-minute stopwatch has not been run.
- **Any of the new pages rendered in a real browser** — same category of gap as every previous
  phase for DOM/Web-Audio-dependent code (`AudioCheckPanel`'s oscillator tone, device enumeration
  labels, the progress page's bar chart, dark/light rendering of five new settings pages). Built
  to spec, code-reviewed, and every piece of *logic* underneath them that doesn't require a real
  `AudioContext`/`MediaDevices` is unit-tested and passing.
- **CI** — no push/CI access in this environment, same standing gap as every previous phase.

### Task 4.6 — recruited sessions (Day 17)

**Explicitly not a coding task, and not executable in this environment.** It needs 10-15 real
booked participants, a live video/audio call, a person taking notes while staying silent, and real
microphones — none of which exist here. Every piece of software the day depends on is built and
tested above: the consent screen presents before any audio check per Task 4.5a's own requirement,
the pre-flight audio check is the real, already-verified pipeline (Task 3.2 AU-09), session
creation and report generation are Phase 0-3's own already-tested paths. What Task 4.6 itself
asks for — booking people, running the calls, writing up usability notes, producing a prioritised
bug list from real sessions — did not happen and could not happen here, and is recorded as
unexecuted rather than silently skipped. Phase 5 (`services/training`, "not deployed" per
CLAUDE.md's own directory layout) explicitly cannot proceed without the real recruited-session
data this day is meant to produce.

## 2026-08-23 — Integrity check: is Phase 4 actually complete, or halted mid-way?

Re-ran everything from a cold state to check for exactly that — no code changes intended, only
verification. `git status` showed the expected 68 changed/new files and nothing else (no stray
`.env`, no cache/build artefacts, no TODO/FIXME/`NotImplementedError` markers anywhere in the new
or touched code). `make lint` (ruff, `mypy --strict` on realtime, mypy on api/coach, eslint,
`tsc --noEmit`) is clean across all four packages. `alembic current` and `alembic heads` both
report `d4e5f6a7b8c9` — the dev DB is genuinely at the migration head, not just hand-patched (the
concern noted when this migration was edited after its first `upgrade head`, above, is resolved).
The frontend suite: **91/91 vitest tests pass.** The backend suite: **606 passed, 1 skipped, 4
failed** on the first full run.

All four failures were individually re-run in isolation and every one passed cleanly — confirmed
run-time flakes, not regressions or unfinished work:

- `test_stage_records_a_row_with_measured_duration` — asserted a 10ms `asyncio.sleep` produces
  `duration_ms >= 10.0`; got 9.6ms once under full-suite load (Windows timer-resolution jitter).
  Passed immediately in isolation.
- `test_initial_prompt_biasing_recognizes_uncommon_term` — the same faster-whisper vocabulary-
  biasing non-determinism already documented as flaky in the Phase 0-2 re-verification section
  above, on the same fixture. Passed immediately in isolation.
- `test_genuine_distress_triggers_the_exit[...-remote]` (2 of the 3 `GENUINE_DISTRESS_CASES`,
  the live-`Groq`-model parametrization) — **this one got real scrutiny rather than being
  waved through**, since it's the AS-07 safety suite CLAUDE.md §7 calls out by name as never
  skipped to make CI green. It is a live, temperature>0 model call asserting the model's reply
  starts with the exact fixed marker `"i'm pausing this practice session."`; a single miss under
  full-suite concurrent load is model sampling variance, not a prompt-compliance regression — but
  that conclusion was earned, not assumed. Re-ran the same two cases in isolation **twice** (6/6
  total): both passed cleanly both times. No change made to the prompt, the marker check, or the
  test — there was nothing to fix, and this exact flake was not previously recorded, so it's
  logged here rather than silently re-run away.

**Conclusion: nothing was left mid-way. Phase 4 is complete, lint-clean, and the full test suite
is green on a true rerun of every test that failed once.** `make lint`, the frontend suite, and
alembic's head state all needed no fixes at all this round — this entry exists to record that a
second, independent pass was made and to name the one new (safety-suite) flake honestly rather
than let a clean second run go undocumented.

## 2026-08-24 — Phase 0-4 re-verification (before starting Phase 5)

Per this session's own instruction to confirm Phase 0-4 before touching Phase 5, a fresh
independent verification pass (a separate agent, no shared context with the prior session's own
claims) re-ran everything from scratch rather than trusting the entry above.

**Reproduced exactly**: `git status` clean at HEAD `606292a` ("version 01234", one commit ahead
of the `47870ca` the prior entry's mid-point references — expected, not a gap: all of Phase 4
plus that entry's own final integrity-check paragraph were committed together afterward).
`ruff check .` clean. `mypy --strict` on `services/realtime/app` (53 files), `mypy` on
`services/api/app` (46 files) and `services/coach/app` (27 files) all clean. `pnpm lint`
(eslint + design-token check) and `pnpm typecheck` clean. Frontend: **91/91 vitest tests**,
exact match. Backend (Docker daemon down at verification start, so testcontainers-dependent
tests errored on missing infra rather than failing on code — 52 such errors, all
`docker.errors.DockerException`, none a real failure): 516 passed, 1 failed
(`test_stage_records_a_row_with_measured_duration`, the same Windows-timer-jitter flake already
on record; passed in isolation), 6 skipped. Repo-wide grep for
`TODO|FIXME|XXX|NotImplementedError|not yet implemented|HACK`: zero hits outside
`services/coach/app/scorer/finetuned.py`'s own deliberate, documented Phase 5 seam and this
file's own prose. Every file changed since `47870ca` traces to a specific line in the Phase 4
narrative above; no undocumented work found.

**Two small, real discrepancies, neither a correctness issue**, recorded here rather than
silently fixed:

1. **Every commit message in this repository's history is a non-conventional placeholder**
   (`"Initial commit"`, `"version012"`, `"version 0123"`, `"version 01234"`) — a real deviation
   from CLAUDE.md §12's mandated `type(scope): subject` convention. The well-documented Phase
   0-4 body of work sits behind commit messages that give no indication of scope or content on
   their own; `docs/PROGRESS.md`'s prose is what actually carries that information. Not fixed
   here (rewriting published commit messages is a destructive history operation this session
   was not asked to perform) — flagged so a future session doesn't assume the git log is a
   usable changelog.
2. Harmless `mypy` "unused section(s)" notes for stub-only third-party modules listed in
   `pyproject.toml`'s override blocks (`botocore`, `faster_whisper`, `onnxruntime`, `piper`,
   `sounddevice`, `services.realtime.*` when checking `api`/`coach` in isolation) — configuration
   noise, not a failure, present on every `mypy` invocation throughout this project's history and
   not previously called out.

**Conclusion: Phase 0-4 is genuinely complete and matches its documentation.** Phase 5 below is
built on top of it, not around it.

## 2026-08-24 — Phase 5: dataset and model-registry infrastructure, honestly short of real data

Built everything in `docs/phase-5-BUILD.md` that can be built without the two inputs this phase
fundamentally depends on and that do not exist in this environment: real recruited-session audio
(Phase 4's Task 4.6 never ran — see that phase's own entry above) and a second independent human
annotator (this session is one model instance; using itself as a second rater would fabricate
the inter-annotator-agreement figure the entire fine-tune claim rests on, directly violating
CLAUDE.md §9 and §10). This gap was flagged to the user before starting; their instruction was to
build everything in full, use clearly-flagged placeholder data only where real data is required,
and write a separate walkthrough document rather than silently working around the gap —
`docs/PHASE5-WALKTHROUGH.md` is that document, and is the companion this entry should be read
alongside.

### What exists now

- **Task 5.1 — the registry tables**: `model_versions`, `eval_runs`, `dataset_revisions` (plus
  `dataset_members` and `pre_labels`, plumbing the task's own table list doesn't name but the
  rest of the phase needs — `docs/decisions/0020`), all real migrations, applied to real
  Postgres. The partial unique index enforcing "exactly one active `model_versions` row per
  role" was verified live by attempting a second active insert for the same role and watching it
  get rejected by Postgres, not just by application code.
- **Task 5.2 — dataset construction**: `services/training/dataset/{build,synthetic,split,
  records,write_synthetic,dev_fixtures}.py`. `split.py` is pure and has 10 unit tests, including
  the acceptance criterion's own deliberately-leaked fixture proving the speaker-leakage
  assertion actually fires. `build.py` was run live against real Postgres twice in a row without
  changing the underlying data and produced the *identical* dataset-revision hash both times —
  TASK 5.2d's own acceptance criterion, verified, not assumed. `synthetic.py` made a real litellm
  call during this session and got back a genuine, on-topic interview question and answer.
  `dev_fixtures.py` exists solely for smoke-testing the rest of the pipeline (clearly tagged
  `@phase5-dev-fixture.invalid`, deleted again after every use — never left in the database, never
  contributing to any number in `docs/RESULTS.md`).
- **Task 5.3 — the annotation tool**: `users.is_admin` (`docs/decisions/0019`) gates
  `/admin/annotate/*` and the new `/app/annotate` page. Real endpoints: `GET queue` (order-
  randomised via `ORDER BY random()`, excludes anything the calling admin already labelled,
  never returns a model prediction — verified by a real test asserting the response's exact key
  set), `POST submit` (round auto-increments per annotator, rejects a mismatched
  `pre_label_score` — TASK 5.3d's "the interface must not default to accept," enforced
  server-side not just in the UI), `GET progress`. 8 real integration tests against testcontainers
  Postgres, including one that proves a second admin account can independently label a
  double-labelled item and that the disagreement-detection logic correctly flags a >1-point gap.
  Verified live end-to-end over real HTTP against the real running API: a queue fetch, a
  submission, a rejected stale-pre-label submission, and a second admin's independent label on
  the same item. `services/training/annotate/iaa.py` computes real quadratic-weighted kappa (13
  unit tests, cross-checked against `sklearn.metrics.cohen_kappa_score` on a known case) and was
  run live against two real submitted labels. `pre_label.py` (Task 5.3d, train-split only,
  writes to the new `pre_labels` table — never `annotations` — since a suggestion is not a
  completed human judgement) is built but was not run live this session (no training-split data
  existed yet at that point in the build to pre-label).
- **Task 5.4 — training**: `services/training/{data,baselines,model,calibration,train}.py`.
  The multi-task DeBERTa-v3-base architecture (shared encoder, one regression head per criterion,
  aux features concatenated before the heads, sigmoid-mapped to the 1-5 scale) is real code, not
  a sketch — `microsoft/deberta-v3-base` was downloaded live from Hugging Face Hub and loaded
  successfully twice this session, and a standalone forward-pass check confirmed the tensor
  shapes are correct end-to-end into the loss computation. The isotonic-calibration guard
  (`calibration.py`) has 4 real tests including one proving it raises the instant anything tries
  to fit on the test split — TASK 5.4's own acceptance criterion ("a test asserts test data is
  never touched"), and `train.py`'s own `assert_no_train_test_leakage` is a second, independent
  check from `split.py`'s (re-verifies against whatever actually loaded into the run, not the
  build step). The majority-class and ridge-on-deterministic-features baselines (rows 1-2) ran to
  completion live, against real Postgres data, and logged real metrics to a real (offline-mode)
  Weights & Biases run. **What did not complete live**: a full forward+backward pass of the
  fine-tune itself. See "What surprised me" below — this is a real, measured finding about this
  environment's hardware, not a gap in the code. Row 8 (LoRA) is coded to be skippable with an
  explicit, printed reason rather than silently omitted or faked (CLAUDE.md §10).
- **Task 5.5 — evaluation and deployment**: `scripts/eval.py` (retiring the Phase 0 stub) is the
  real `make eval` implementation — computes QWK/MAE/Spearman/adjacent-accuracy/ECE, fairness
  deltas (speaking rate and vocabulary richness are real computations; "accent group" is reported
  as `"not collected - no such field exists in this schema"` rather than a fabricated proxy,
  CLAUDE.md §10), and the `--publish` gate on the test split. Verified live, three ways: a
  validation-split run succeeded without the flag, a bare `--split test` run was refused (exit 1,
  no `eval_runs` row written), and `--split test --publish` succeeded and logged the access.
  `services/training/eval/generate_results.py` generates `docs/RESULTS.md` from the real
  database — run live, produced a real file with the human ceiling correctly reported as
  unmeasured rather than invented. `services/api/app/services/model_registry_service.py`
  (`promote`/`rollback`) is real, DB-backed logic: promotion requires every one of the
  candidate's published test-split seed kappas to individually beat the current active version's
  — "not on one lucky run" — enforced in code, not just described; rollback is unconditional, a
  pure status change. Exposed at `/admin/registry/*`, admin-gated like the annotation tool.
  Shadow mode (`docs/decisions/0021` — a new `shadow_scores` table, not a widened `turn_scores`
  constraint) is wired into the real `score_turn` path behind a 10%-default sample rate; the
  sampling decision itself has 5 real unit tests, including one confirming the observed rate
  over 5,000 trials lands within 3 percentage points of the configured rate.
- **Task 5.6 — the honest fallback**: this entire entry, `docs/RESULTS.md`,
  `docs/PHASE5-WALKTHROUGH.md`, and the README's new Status paragraph all say the same thing in
  their own register: the prompted scorer ships as the labelled baseline, the fine-tune
  infrastructure is real and tested, and a real trained model with a real human-agreement ceiling
  is Phase 5's actual next milestone, not a claimed-but-unverified result.

### Real bugs this session's own live testing found

1. **DeBERTa-v3's tokenizer cannot load without `sentencepiece` installed explicitly** —
   `transformers`' fallback tiktoken-based conversion path fails on `spm.model` with an opaque
   `ValueError` deep inside `tiktoken.load.load_tiktoken_bpe`, not an informative "install
   sentencepiece" error. Found on the first live training attempt; fixed by adding it to
   `services/training/pyproject.toml`.
2. **Two SQL-tuple-membership calls needed `sqlalchemy.tuple_()`, not `func.row()`** —
   `annotate_service.py::get_queue`'s "exclude anything this admin already labelled" filter and
   an early draft's distinct-pair count both needed rewriting once run live; `func.row()` does
   not render as a usable composite comparison in a `.notin_()`/`.in_()` clause the way
   `tuple_()` does.
3. **A SQLAlchemy `Row` object's `.index` attribute collides with the standard library's own
   `tuple.index` method** — selecting `Turn.index` unaliased into a raw `select()` (rather than
   through the ORM) meant `row.index` silently returned a bound method, not the column value,
   until the column was explicitly `.label("turn_index")`d. Caught by static analysis before a
   live run, not by a test — worth recording since it is a genuinely non-obvious footgun anyone
   extending `annotate_service.py` could hit again.

### What was verified by actually running it

- **Every backend file this phase touched or added**: `ruff check .` and `mypy` (on
  `services/api/app` and `services/coach/app`) both clean.
- **21 new backend unit tests** (`tests/unit/training/{test_dataset_split,test_metrics,
  test_calibration}.py`) and **5 new coach unit tests** (`tests/unit/coach/test_shadow_mode.py`),
  all passing, run directly against the source (not mocked away from the thing under test).
- **8 new integration tests** (`tests/integration/test_phase5_annotate.py`) against real
  testcontainers Postgres, all passing.
- **A live, multi-endpoint smoke test against the real running API** (`make up`'s real
  Postgres/Redis/MinIO, a real `uvicorn` process, a real admin account minted via
  `scripts/grant_admin.py` and a real access token): `GET /admin/annotate/queue`,
  `POST /admin/annotate/submit` (including the rejected-stale-pre-label case),
  `GET /admin/annotate/progress`, and the same sequence again from a second real admin account
  to prove independent double-labelling — all against real rows written by a real
  `dataset/build.py --dev-fixtures` run, cleaned up afterward.
- **`dataset/build.py` run twice back-to-back without re-seeding**, producing the identical
  dataset-revision hash both times — the actual reproducibility acceptance criterion, not an
  assumption about the hashing logic.
- **`scripts/eval.py` run three ways live**: validation (succeeded), test without `--publish`
  (refused, exit 1), test with `--publish` (succeeded, logged).
- **`services/training/eval/generate_results.py` run live**, producing a real `docs/RESULTS.md`.
- **`services/training/train.py --rows 1,2 --skip-frontier` run live to completion**, real
  metrics logged to a real offline W&B run.
- **A partial unique index violation attempted directly against Postgres** (`docker compose exec
  postgres psql`) to prove `model_versions`'s "one active per role" constraint is real, not just
  asserted in a docstring.

### What surprised me

- **CPU-only DeBERTa-v3-base training is slow enough to matter, the same way Piper's cold start
  (Phase 1) and `faster-whisper`'s CPU inference (Phase 2) were.** Two separate live attempts at
  `train.py --rows 5 --seeds 1 --epochs 1` — one bounded by an explicit timeout, one left to run
  unbounded in the background — both got past dataset loading, the leakage assertion, and a
  genuine `microsoft/deberta-v3-base` download-and-load from Hugging Face Hub, then spent the
  remainder of their available time inside the training loop's first forward+backward pass
  without completing it. A standalone, minimal forward-pass check (three tiny examples, no
  training loop, no download since the model was already cached) confirmed the architecture
  itself is wired correctly end-to-end into a working `loss.backward()` call, isolating the slow
  part to the transformer's own CPU compute rather than to a bug. This is a real, measured
  property of this specific environment's hardware, not a defect in the training code — the same
  code is expected to complete "in under 20-30 minutes on a free T4" (the phase doc's own
  estimate) on the GPU runtime `docs/PHASE5-WALKTHROUGH.md` recommends.
- **Eleven real users already existed in the dev database** from Phase 0-4's own live testing
  across every previous session, and precisely zero of their turns satisfied the
  `training_consent=true` eligibility filter `dataset/build.py` requires — confirming, concretely
  rather than theoretically, that Phase 4's consent defaults (training consent off unless
  explicitly turned on) worked exactly as designed, and that this project's own prior live
  testing correctly never became a backdoor source of "real" training data without explicit
  consent.

### What I could not verify by running it

- **Any real number in `docs/RESULTS.md`.** Every metric this session computed was against
  either near-zero real consented data or explicitly-flagged, deleted-afterward placeholder
  data. `docs/PHASE5-WALKTHROUGH.md` is the complete, concrete plan for closing this gap; nothing
  in it requires further engineering, only real data collection and a real second annotator.
- **A completed fine-tune training run** (see "What surprised me" above) — the code path is
  real and partially exercised live; a finished checkpoint was not produced in this session.
- **The LoRA ablation row (Task 5.4d) run for real** — coded to skip with an explicit printed
  reason in this environment rather than fake a result; genuinely running it needs real data and
  meaningful GPU time neither of which existed here.
- **Shadow mode accumulating real comparison data over live traffic** — the wiring is real and
  unit-tested, but no real user traffic has flowed through `score_turn` with shadow mode enabled
  yet in this environment (Phase 4's own recruited-session gap applies here too).
- **CI** — no push/CI access in this environment, the same standing gap every previous phase has
  recorded.

## 2026-09-17 — Phase 6: proof and polish

Every task in `docs/phase-6-BUILD (1).md` has code. Several acceptance criteria are honestly not
met, and each is listed below with the measured reason. The owner permitted invented data and
autonomous fine-tuning for this phase. Synthetic data was used only where it is labelled and makes
no claim about humans (the load test, fixtures, the demo's scripted answers). No human labels and
no agreement figure were invented (docs/decisions/0027).

### What exists now

- **6.1 Observability** (`/app/observability`, admin): e2e percentile header queried directly from
  `latency_events WHERE stage='e2e'`, with the 1400 ms target line drawn and filters for window,
  scenario family and host class (`latency_events.host_class`, new); a stage breakdown stacked in
  pipeline order; a turn waterfall (bars, ms labels, click a stage for its `model_calls` row, user
  audio cut from the recording, persona audio regenerated via an admin replay token); a sortable,
  filterable model-call table with cache hit rate; a cost panel (actual, frontier counterfactual
  priced from `content/pricing/frontier.yaml` using measured judge token means, and the ratio).
  Covering index `ix_latency_events_stage_created_at_cover`. Migration `b8c9d0e1f2a3`.
- **6.2 Evaluations** (`/app/evals`, admin): model registry with confirm-then-promote/rollback
  (status changes through the Phase 5 registry service, which now writes `deployment_events`);
  suite results; a per-case grid (human labels vs model score, linking to the report, sorted by
  disagreement descending); a regression chart with deployment markers; a two-version comparison
  over identical cases (`turn_scores` ∪ `shadow_scores`), disagreements first; a speech panel.
- **6.3 Suites**: `make eval-speech` (`scripts/eval_speech.py`), `make eval-persona`
  (`scripts/eval_persona.py`, judge prompt `content/prompts/eval/persona-judge.v1.md`),
  `.github/workflows/nightly-eval.yml` (all three levels, job summary via
  `scripts/publish_metrics.py`, opens or updates a `nightly-eval` issue on failure). New fixtures:
  technical-vocabulary and accented clips plus `tests/fixtures/audio/manifest.json`, and
  `tests/fixtures/persona/candidate_scripts.json`.
- **6.4 Deployment**: Dockerfiles for api, coach, realtime and web; `deploy/fetch_models.py` (weights
  downloaded on first boot into a volume); `compose.selfhost.yml` (Ollama, local login, one-shot
  model fetch and migrate/seed); realtime loads models in a background task (liveness up
  immediately, readiness 503 until loaded, sockets refused with 1013 meanwhile), drains on SIGTERM
  (`drain_sessions`, `SHUTDOWN_DRAIN_TIMEOUT_S`), and the client shows "At capacity, try again
  shortly" on close 4429. `docs/18-deployment.md` covers topology, affinity, memory sizing and the
  production env checklist, including second OAuth apps.
- **6.5 `/demo`**: a static bundle (`apps/web/public/demo/`) exported through the API's own
  serializers from a session recorded through the live pipeline (`scripts/record_demo.py`,
  `scripts/export_demo.py`) and rendered by the real report components (`ReportHeader`,
  `Waveform`, `VerdictBlock`, `ScorePanel`, `DeliveryPanel`, `Transcript`, each with a `readOnly`
  mode), with a guided 60-second tour that seeks to a verified evidence span.
- **6.6 Landing** at `/` (sign-in moved to `/signin`): hero, a playable audio proof strip with
  measured per-turn latency, three screenshot panels, an SVG two-agent diagram, an evaluation
  callout with provenance on every figure, a one-click self-host command, and a footer that says it
  does not predict hiring outcomes.
- **6.7 Docs**: README rewritten to the required structure; decisions 0022–0027;
  `docs/DEMO-VIDEO-SCRIPT.md`.

### Real bugs found by running things live

1. **Every live user turn failed to persist** (`turns.training_excluded` NOT NULL with no default
   since Phase 4; realtime never set it), so the persona never replied. Fixed, with a regression test
   confirmed red first (decision 0023).
2. **The coach never scored live turns**: `enqueue_score_turn` was never called on the turn path.
   Fixed; verified by a live session producing 32 `turn_scores` rows and a ready report.
3. **`docker-compose.yml` pinned the network name**, so the self-host stack joined the dev stack's
   network and `postgres` resolved to both databases. The self-host API wrote one
   `local@selfhost.invalid` user into the dev DB, which was deleted. The network is now
   project-scoped.
4. **The standalone Next build fails on Windows** (symlink permission); it is now opt-in and used
   only in the Dockerfile. pnpm 11 needs Node ≥ 22 (web image moved to `node:22`).
5. **The post-generation check does not catch praise** (found by Level 2, not fixed; see results).

### Measured results

- Speech (eval_runs `01a0ac1e`): WER 0.052 overall (clean 0, accented 0, technical 0.156), ASR RTF
  0.13, TTS RTF 0.11, endpoint precision 0.573 / recall 1.0 over 220 boundaries, **passed**.
- Latency on `dev-laptop-cpu`, n = 8: p50 3,576 / p90 4,774 / p95 5,936 ms. **Budget not met.**
- Persona, local `qwen2.5:3b` (eval_runs `01a0aca9`): break rate 0.05 (3/60, all praise); tiers
  separated on follow-up rate only (p = 0.042; ack p = 0.30, interruptions p = 0.88). **Failed,
  correctly.** Broken-prompt check (eval_runs `01a0acaf`): 0.75.
- Persona on hosted `gpt-oss-20b` (eval_runs `01a0ac90`): **invalid**. Groq's free-tier daily token
  quota ran out mid-run, so 55/60 replies were canned deflections. Not published.
- Live safety suite: 33/36. The 3 failures are the hosted-model distress exits, run while that
  quota was exhausted; all 18 local-model cases passed. Re-run when the quota resets.
- Images (`docker images`): api 351 MB (met), coach 776 MB (target 400, missed), realtime 1.08 GB
  (target 800, missed); no weights in any layer (decision 0026).
- Lighthouse performance (mobile, throttled, 3 runs): `/` 0.99 / 0.98 / 0.89; `/demo`
  0.85 / 0.87 / 0.90.

### Verified by running

- 633 pytest (unit + integration, including 10,000-event observability load under 2 s and an
  EXPLAIN check on the covering index, local login, drain, liveness/readiness), 92 vitest, ruff,
  ruff format, mypy (strict on realtime), eslint, tsc, `next build`.
- `/demo` and `/` served 200 from `next start` with api, realtime and coach stopped.
- Self-host from a fresh clone with volumes removed: all services healthy, migrate and seed applied,
  local sign-in issued a token, and a replayed voice session ran through VAD, ASR, persistence,
  MinIO upload, coach jobs and a clean close.

### Not done / not verified

- **Deployed instance**: not deployed (needs Vercel/Neon/Upstash/R2/HF credentials outside this repo).
- **Recorded 3-minute video**: not recorded; needs a human voice (script written).
- **Resume and skills section**: outside this repository; not touched.
- **Scorer agreement vs the human ceiling**: no human-labelled split exists (decision 0027).
- **Self-host persona replies**: on this CPU-only laptop, `qwen2.5:3b` in Docker exceeds the 12 s
  thinking watchdog, so replies degraded to the holding line.
- **SIGTERM drain against a live socket in a container**: covered by unit tests only.
- **At-capacity close against a live server**: covered by handshake and client unit tests only.
- **Nightly workflow**: written, not yet run on GitHub (needs the `GROQ_API_KEY` secret).
- **Observability and evaluations pages in a browser with real admin data**: API integration-tested
  and type-checked; not visually checked while signed in.
