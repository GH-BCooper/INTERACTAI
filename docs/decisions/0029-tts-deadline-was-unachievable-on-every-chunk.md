# 0029 — The 400ms TTS deadline was unachievable on every chunk, so no user ever heard the persona

## Context

An end-to-end run of the CLI voice harness (`scripts/cli.py --replay`) against a live realtime
service reached the persona and came back with the turn intact but **no persona audio at all**:

```
  ♪ [persona] "Thanks for coming in."
  ⚠ degraded: tts — Opening line synthesis missed its deadline.
  ...
  ⚠ degraded: tts — Synthesis failed; playing a holding line.
```

Every chunk of every reply — opening line included — fell through `synthesize_with_deadline`'s
timeout path twice and played the holding line. The degradation policy (CLAUDE.md §6) worked
exactly as designed: the session stayed alive, the incident was logged, the turn finalised, the
score was produced. That is precisely why this survived. Nothing crashed, nothing failed a test,
and the 644-test suite was green throughout. The product simply never spoke.

## Investigation

Three independent faults stacked, each of which alone would have been survivable.

**1. `intra_op_num_threads = 1` was the wrong end of the curve.** Decision 0011 set it there off
a benchmark that measured the first few calls after a voice load. Those calls are
unrepresentatively fast (~110-170ms) at *any* thread count; the session then settles two to four
times higher. Measuring steady state instead (4 warm-up calls, then median and max of 10, idle
machine, `en_US-lessac-medium`):

| `intra_op_num_threads` | short sentence p50 / p95 | 14-word sentence p50 / p95 |
|---|---|---|
| 1 | 470 / 537 ms | 1567 / 1589 ms |
| 2 | 310 / 322 ms | 957 / 985 ms |
| 4 | **219 / 258 ms** | **717 / 767 ms** |
| 5 | 373 / 390 ms | 1009 / 1614 ms |
| 8 | 664 / 728 ms | 1719 / 1797 ms |
| default (16 logical cores) | 841 / 916 ms | 1465 / 1572 ms |

0011's finding — that the onnxruntime default is bad for a VITS-sized graph — still holds. Its
*chosen value* was wrong: 1 and the default sit on opposite sides of the same curve, and 4 is its
floor on this hardware. At 1, the floor of the primary voice's p50 was above the 400ms deadline,
so the fallback voice was attempted and missed it too, on every single chunk.

**2. `FIRST_CHUNK_MAX_WORDS = 12` never fit the deadline.** Synthesis cost is roughly linear in
words. At the corrected thread count, p95 of 8 calls: 6 words 310ms, 8 words 669ms, 12 words
633ms, 16 words 880ms. Only a cap of 6 fits 400ms with margin. `docs/phase-2-BUILD` Task 2.4 asked
for exactly this measurement ("test 8 / 12 / 16 and measure `tts_first_chunk`") and it had never
been done — 12 was a guess that was never checked against the deadline it had to satisfy.

**3. The flat deadline was applied to *every* chunk, not just the first.** `turn.py::_emit_chunk`
and `persona/opening.py` both passed the default `CHUNK_DEADLINE_MS` for every chunk, while
`CHUNK_MAX_WORDS` allows 40. A 400ms budget for up to 40 words of synthesis is not a deadline that
can be met; it is one that reports failure. Even with faults 1 and 2 fixed, any sentence past
about six words would still have spoken a holding line *in the middle of the reply*.

## Decision

- `PIPER_INTRA_OP_THREADS = 4`, from the steady-state table above, with the benchmark recorded in
  `_load_voice`'s docstring. `inter_op_num_threads` stays 1 — the graph has no parallel branches.
- `FIRST_CHUNK_MAX_WORDS = 12 → 6`, the tuning Task 2.4 specified, against measured p95.
- `deadline_for_chunk(text, is_first_chunk=...)`: the first chunk keeps the spec'd 400ms, because
  it is the only chunk the user waits on in silence. Later chunks get
  `max(400ms, 90ms × words)` — they are synthesised while already-sent audio plays, so their real
  constraint is "ready before the queue drains", and Piper runs roughly 5x faster than playback.

`CHUNK_DEADLINE_MS` itself is unchanged at the spec'd 400ms. What changed is the scope it is
applied to (time-to-first-audio, which is what the number was always about) and making the
pipeline able to meet it.

## Consequence

The persona is now audible. A real first chunk, sized by the real chunker cap and synthesised by
the real committed voice, completes in ~219ms p50 / ~258ms p95 against the 400ms deadline.

The holding-line fallback stays, for the reason 0011 already gave: a slow chunk is still possible
under real concurrent load. What it no longer is, is the only thing the user ever hears.

## What this says about the test suite

The lesson worth more than the fix: **644 passing tests, `mypy --strict` clean, and a green CI
did not notice that the product never spoke.** The unit tests around this code are good tests —
they assert that a slow synth falls back to the secondary voice, and that a slower one falls back
to the holding line. Both pass whether the real engine takes 50ms or 5 seconds, because both inject
a fake `synth`. The deadline *orchestration* was covered; whether the real engine could meet the
real deadline on a real chunk was covered nowhere.

`test_real_first_chunk_synthesis_meets_its_deadline` closes that gap: real voice, real chunker cap,
real deadline, no injected timing. It fails on the pre-fix constants and passes after. Any future
change that pushes synthesis back over the deadline — a model swap, a thread-pool regression, a
larger first-chunk cap — now fails a test instead of silently replacing the persona with
"Sorry, one moment."
