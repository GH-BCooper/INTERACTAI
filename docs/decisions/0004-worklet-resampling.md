# 0004 — one streaming linear-interpolation resampler, not two code paths

**Phase:** 1 (Task 1.2a)

## The spec

> Resample from `sampleRate` (usually 48000) to 16000. Integer-ratio decimation is acceptable
> and must be documented here. Non-integer ratios use linear interpolation.

Read literally, that's two branches: a decimation path for e.g. 48000 Hz (ratio 3.0) and an
interpolation path for e.g. 44100 Hz (ratio 2.75625).

## Decision

`capture-processor.js` implements **one** streaming linear-interpolation resampler
(`_feedResampler`) for every ratio. There is no separate decimation branch.

## Why this still satisfies the requirement

The resampler tracks a fractional output position `nextOutPos` in input-sample units and, for
each new input sample, emits an interpolated output sample whenever `nextOutPos` falls at or
behind the newest input sample:

```
output[k] = input[floor(nextOutPos)] + frac * (input[floor(nextOutPos)+1] - input[floor(nextOutPos)])
nextOutPos += ratio
```

For an **exact integer ratio** (48000/16000 = 3.0), `nextOutPos` is an integer after every
increment, so `frac` is always exactly `0` and the formula degenerates to
`output[k] = input[3k]` — literal decimation, arithmetically, with no special-casing. For a
**non-integer ratio** (44100/16000 = 2.75625), `frac` varies and the same formula performs
genuine linear interpolation.

One tested code path covers both documented cases instead of two, which is less code and one
fewer place for a boundary bug (e.g. an off-by-one at the branch condition) to hide. This is a
simplification within what the spec asked for, not a deviation from it — the observable
behaviour (decimation when the ratio is integral) is unchanged.

## Cost accepted

A very small extra latency: because the interpolation formula technically needs the input
sample *after* `floor(nextOutPos)` even when its weight (`frac`) is zero, an integer-ratio
stream waits for one extra input sample before each emission compared to naive decimation.
At 48 kHz that is ~1/48000 s (≈0.02 ms) per frame — several orders of magnitude below anything
in the latency budget, and not worth a second code path to avoid.

## What was not built

A polyphase or windowed-sinc resampler. `docs/phase-1-LEARN.md` §3 explicitly says not to:
"Do the simple thing... Do not build a polyphase resampler." Mild aliasing from linear
interpolation is inaudible at speech quality and Whisper does not care (same doc, same
section).

## What remains unverified

This algorithm is verified by hand-derivation (see the code comment) and exercised indirectly
by `apps/web/lib/audio/capture.test.ts` for the framing/sequencing logic downstream of it, but
`capture-processor.js` itself cannot run under vitest's Node environment (`AudioWorkletProcessor`
and `registerProcessor` don't exist outside a real browser's audio-rendering thread). A real
5-minute browser capture session (Task 1.2 acceptance criteria) is the only way to confirm the
resampler behaves correctly under real scheduling — that is manual, in-browser verification
this build could not perform, and it is flagged as such in the Phase 1 report.
