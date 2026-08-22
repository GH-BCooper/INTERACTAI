# 0008 — Phase 2 state machine: protocol_version 1.1, and four deliberate deviations from the Task 2.1 table

Task 2.1 (`docs/phase-2-BUILD.md`) asks for a formal 9-state machine that supersedes Phase 1's
ad-hoc one (`docs/decisions/0001-realtime-state-machine.md`). That table adds `interrupted` and
`closing` as real, client-visible states and renames every `client_state` value. Both are
changes to the frozen WS message schema (`packages/schema/ws-messages.schema.json`,
CLAUDE.md §1.3). Decision 0001 explicitly anticipated this: *"if Phase 1 needs a finer split...
it is a schema change caught by the schema-drift CI job — not a silent drift."* This doc is
that schema change, done as the versioned migration CLAUDE.md requires rather than a silent
refactor.

## What changed

- `protocol_version` minor bump: `"1.0"` → `"1.1"`. **Major stays `1`** — `main.py`'s handshake
  only checks the major component, so this is additive/non-breaking for any client still
  claiming `"1.x"`.
- `server_machine_state` enum: `connecting, idle, listening, endpointing, thinking, speaking,
  degraded, closed` → adds `interrupted`, `closing`.
- `client_state` enum: `listening, thinking, speaking, degraded` → replaced with
  `your_turn, thinking, speaking, connection_trouble, ended` (Task 2.1's table). This is a
  rename, not additive — anything reading the old string values breaks. Nothing outside this
  repo consumes the WS protocol yet (no web UI ships before Phase 3), so there is no live
  client to migrate.

## Four places the implementation deviates from Task 2.1's literal table, and why

1. **`connecting` is kept**, with `connecting → idle | closed`, even though it doesn't appear
   in Task 2.1's table at all. It is the pre-`hello` bootstrap state from Task 1.1's handshake
   sequence (`docs/phase-1-BUILD.md` Task 1.1), which Task 2.1 doesn't re-describe or ask to
   remove. Dropping it would mean the state machine has no valid state to be in between
   "socket accepted" and "hello acknowledged," which is a regression, not a simplification.

2. **`endpointing → idle` is kept legal**, even though Task 2.1's table only gives endpointing
   `{thinking, listening, closing, degraded}`. Task 1.3c's minimum-utterance-length guard
   ("a shorter detection is noise, discarded, state returns to `idle` without creating a
   turn") fires from exactly this transition and is still in force — Task 2.1 doesn't mention
   or supersede it. Routing a discarded cough through `listening` instead would leave
   `current_utterance` `None` while in a state that assumes one exists
   (`frame_pipeline._current_utterance` raises if it's missing), which is a real bug, not a
   spec-fidelity nicety. Table gap, not intent — documented instead of guessed silently.

3. **`listening`'s `aborted` target is implemented as a legal self-transition
   (`listening → listening`)**, not a tenth enum value. `aborted` appears exactly once in the
   Task 2.1 table, with no row in the timeout table, the `client_state` mapping, or anywhere
   else in the document — it names an *event* (a candidate utterance was thrown out as noise
   while still in `listening`), not a state a client should ever be told about. Minting a real
   `aborted` enum member would need to appear in `client_state` too (Task 2.1: "the eight
   \[sic — nine] machine states collapse to four \[sic — five] the user perceives"; an
   undocumented fifth server state with no client mapping breaks that closure). A same-state
   transition satisfies "any transition not in this table raises `IllegalTransition`" — it's in
   the table, once — while emitting a `state_transition` log line (see below) that already
   distinguishes an aborted candidate from ordinary continued listening via its metadata.

4. **`idle → thinking` is added**, even though Task 2.1's table gives `idle` only
   `{listening, closing, degraded}`. Task 2.3f's scripted opening line needs the persona to
   start generating and speaking *before any user utterance exists* — there is no preceding
   `endpointing → thinking` hop to ride, and `idle` is the only state the session is in at that
   point. Without this addition the very first thing the opening-line delivery path
   (`persona/opening.py`) does would raise `IllegalTransitionError`. Task 2.1's table was
   written without this later sub-task's requirement in view; this closes that gap rather than
   working around the state machine.

## Where "a `latency_events` row for the state it is leaving" actually goes

Task 2.1 says every transition emits "a structured log line and a `latency_events` row for the
state it is leaving." `latency_events.stage` is a CHECK-constrained enum
(`endpoint_detect, asr_finalize, prompt_assemble, model_ttft, first_chunk_assemble,
tts_first_chunk, transport, e2e`) that CLAUDE.md §8 states explicitly and is covered by a CI
constant test (`docs/phase-1-BUILD.md` Task 1.2d / 1.6a). Widening a CHECK-constrained,
CI-locked enum on the strength of one clause in a later phase doc, when CLAUDE.md itself lists
the eight names as fixed, is exactly the kind of contract change CLAUDE.md says to ask about
first rather than do silently — and unlike the `client_state` rename above, there is a
same-precedent way to honor the *intent* without touching a second frozen contract:
`docs/decisions/0005-latency-stage-metadata.md` already chose "structured log, not a schema
change" for exactly this kind of supplementary timing data (ASR's RTF). This decision applies
that same precedent: every transition writes a `state_transition` structlog line
(`session_id`, `turn_id` if one is live, `from`, `to`, `at_ms`, `duration_in_state_ms`), which
reconstructs the turn timeline exactly as well as a dedicated table would, without a second
CHECK-constraint migration on top of the `client_state` one this doc already makes. If a later
phase wants that queryable in SQL rather than logs, it's a new decision, not an inference from
this one.

## The `speaking` timeout is approximated, not measured against "reply duration"

Task 2.1's timeout table gives `speaking` a deadline of "reply duration + 5 s." Total reply
duration isn't knowable in advance — chunks are generated and played incrementally
(Task 1.5), and the whole point of streaming TTS is that the server never buffers the full
reply before sending. The implementation instead tracks *time since the last audio chunk was
sent* and treats 5 s of silence with no forward progress while still in `speaking` as the
timeout — the same failure mode (playback stalled, no more audio coming) with a measurable
trigger instead of an unknowable one.

## Live-run finding: the literal 200ms `endpointing` timeout was wrong, not just strict

The first full `scripts/cli.py` run against the real stack with the real persona (not
`--persona-stub`) showed the watchdog firing "Endpoint decision took too long" repeatedly
during entirely ordinary listening/endpointing cycling, before the actual utterance was even
reached. Investigating rather than dismissing it as noise: Task 1.3b's cascade legitimately
holds the `endpointing` state for up to `ENDPOINT_MAX_SILENCE_MS` (900ms) of silence
accumulation, plus up to `MAX_EXTENSIONS_PER_UTTERANCE` (2) filler/syntax extensions
(300ms/250ms each), plus the semantic check's own 80ms timeout — roughly 1.5s of genuine,
by-design dwell time in the worst case. A 200ms state-level timeout was firing on normal
cascade operation, not hangs; the state machine's own watchdog was the bug, not the cascade.
Fixed by raising `STATE_TIMEOUT_MS[endpointing]` to 2000ms — comfortable margin above the
legitimate worst case, while still catching a genuine stall. This is exactly the kind of thing
CLAUDE.md §13 asks to surface honestly: a defensible-looking number from the spec, disproven by
actually running the system rather than trusting the arithmetic on paper.

## Live-run finding: the literal 5000ms `thinking` timeout was far worse than wrong — Task 2.4

The same pattern recurred, more severely, while gathering Task 2.4's e2e latency numbers. A
55-turn batch (`scripts/cli.py` replay, both `--persona-stub` and real-persona, one session at a
time, nothing else competing for the machine) against `STATE_TIMEOUT_MS[thinking] = 5000.0`
completed **0 of 55** turns — every single one hit the `thinking` watchdog and degraded before a
reply was ever produced, stub or real. Root cause: `asr_finalize` (faster-whisper `base.en`/
int8, this project's CPU-only dev hardware) alone measured 2.5-8.2s across isolated benchmark
runs, so ASR by itself frequently consumes the entire 5000ms budget before a persona reply has
any chance to start, let alone finish — this has nothing to do with the persona model call; a
`--persona-stub` turn (canned reply, no network call) failed just as often as a real one.

This is a more consequential finding than the endpointing one above: it isn't "the watchdog fires
during normal operation" (annoying, logged, recoverable), it's "the watchdog prevents the system
from completing a turn at all, essentially always, on this hardware." Fixed by raising
`STATE_TIMEOUT_MS[thinking]` to 12000ms — margin above the worst observed ASR call plus a
persona TTFT on top. This does not change the *content* of Task 2.4's honest latency report
(`docs/PROGRESS.md`): ASR being this slow on CPU-only hardware is still the dominant reason the
1400ms e2e budget isn't met, and that finding stands regardless of this fix. What this fix
changes is whether a turn on this hardware completes *at all* — without it, the "measure e2e p50/
p95 over ≥50 real turns" acceptance criterion is not just slow to satisfy, it's structurally
impossible, since a turn that degrades at the `thinking` timeout never reaches the point where
`e2e` gets recorded. Not a metric to game — a precondition to fix before the metric means
anything.
