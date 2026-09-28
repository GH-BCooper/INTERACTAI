# 0031 — The TTS chunk deadline caused most of the misses it was detecting

## Context

After 0029 made the 400ms chunk deadline achievable (219ms p50 in isolation), live sessions still
degraded to a holding line on roughly half of all replies — including on chunks as short as
`"Okay."`, one word, which synthesises in well under 100ms on its own. An isolated benchmark and a
live session disagreed by an order of magnitude, which is usually a sign that the measurement is
not measuring what the live path does.

## Investigation

The difference is that a live path synthesises chunks *back to back*. Benchmarking the same 48
chunks (four realistic replies, real chunker splits, both voices pre-warmed) the way the service
actually calls them, versus the same sequence with no deadline at all:

| | outcome |
|---|---|
| with the deadline and its secondary-voice retry | 25/48 chunks missed, p50 719ms, p95 2537ms |
| identical sequence, nothing ever abandoned | p50 142ms, p95 424ms, **3/48** genuinely over 400ms |

The deadline mechanism was manufacturing roughly eight times the failures it caught.

The cause is that `synth` ends in `asyncio.to_thread`, and **a thread is not cancellable**. When
`asyncio.wait_for` gives up, the abandoned synthesis does not stop — it runs to completion, still
holding its ONNX Runtime threads. The old code then immediately re-synthesised the same text on
the secondary voice, putting a second CPU-bound job against the first. The retry missed the same
deadline for the same reason, the holding line played, and *both* orphans were still running when
the next chunk started. Each miss made the following chunk likelier to miss. `"Okay."` was not
slow; it was queued behind the wreckage of the chunk before it.

This is why it read as flaky rather than broken: the first chunk of a session usually made it, and
everything after the first miss compounded.

## Decision

Split the two cases that Task 1.5b treats as one ("if a chunk takes > 400 ms to synthesise, fall
back to the secondary voice"):

- **Timeout → the holding line, immediately, with no second synthesis.** The deadline is already
  spent by the time we know it was missed, so a retry cannot win it back; all it can do is damage
  the chunks that follow.
- **Exception → the secondary voice**, as before. A missing voice file, a corrupt model or an
  engine crash leaves nothing running, so the retry is free and can genuinely succeed. This is
  what a fallback *voice* is for, as opposed to a fallback *deadline*.

This contradicts the letter of Task 1.5b, which is why it is written down here. It serves the
spec's intent — get audio to the user fast, degrade rather than die — which the literal rule was
actively defeating.

## Consequence

Re-measured, same 48 chunks, same conditions:

| | missed | p50 | p95 |
|---|---|---|---|
| before | 25/48 (52%) | 719ms | 2537ms |
| after | **0/48** | **68ms** | **142ms** |

The holding line now fires on genuine engine trouble rather than on its own contention. A new
`tts_chunk_missed_deadline` log event records a real miss, so the case stays visible instead of
being inferred from the absence of audio.

## What this says about deadlines on uncancellable work

Generalisable, and the reason this is a decision record rather than a commit message: **a timeout
around work you cannot cancel is not a timeout, it is a notification.** The work continues and you
have no way to reclaim what it is consuming. Any retry scheduled off that notification competes
with the thing it is replacing, so on a saturated CPU the retry is *slower* than the original, not
faster — the more urgently the code retries, the worse it does.

`asyncio.wait_for` makes this easy to get wrong because it looks like cancellation and reads like
cancellation, and against a coroutine it is. Against `to_thread` it is a stopwatch. Worth checking
the other `wait_for`-around-`to_thread` sites (VAD, ASR) for the same shape before assuming this
was the only one; they were not implicated by this measurement and have not been re-measured.
