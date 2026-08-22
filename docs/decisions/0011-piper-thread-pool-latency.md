# 0011 — Piper's default ONNX Runtime thread pool was the real opening-line latency bug

## Context

Live CLI testing of Task 2.3f (the scripted opening line) showed `synthesize_with_deadline`
missing its 400ms `CHUNK_DEADLINE_MS` on essentially every run, for both the primary and
secondary voice, even after both were pre-warmed at startup (`BackchannelCache` /
`IdlePromptCache` preload for every `persona_voice_ids` entry, several real synthesis calls
per voice before any session exists). That ruled out Phase 1's original "cold process" theory
(`docs/PROGRESS.md`, "What surprised me") — the process was already warm.

## Investigation

Direct benchmarking (`PiperVoice.load()` + `voice.synthesize()`, no asyncio, no wrapper code)
showed the *first* call after loading a voice was fast (~100-160ms) but every call after it,
on the same already-loaded voice, in complete isolation (nothing else loaded, single script,
otherwise idle machine) settled at 650-900ms — the opposite of a warm-up curve. Reducing
`onnxruntime.SessionOptions().intra_op_num_threads` from its default (one per physical core —
10 on this machine) down to 1 collapsed that to 95-335ms, consistently. A/B, same model, same
sentence, 6 calls each:

| `intra_op_num_threads` | calls (ms) |
|---|---|
| 10 (default) | 916, 839, 726, 725, 890, 755 |
| 4 | 315, 271, 170, 179, 164, 146 |
| 1 | 162, 110, 95, 281, 335, 328 |

This is a known ONNX Runtime footgun for small models: a VITS-sized graph has too little
parallel work per op for a 10-wide intra-op thread pool to pay for itself — the wake/
synchronize/join overhead across that many worker threads exceeds the compute it parallelizes,
and it's Windows-scheduler-sensitive on top of that (thread wake latency is worse than Linux).
`piper.PiperVoice.load()` doesn't expose `sess_options` as a parameter, so there was no way to
fix this by passing a flag.

## Decision

`services/realtime/app/tts/piper.py::VoicePool` no longer calls `PiperVoice.load()`. It builds
the `onnxruntime.InferenceSession` itself (`_load_voice`), replicating exactly what
`PiperVoice.load()` does internally (same config-loading, same `CPUExecutionProvider`), with
`intra_op_num_threads=1` and `inter_op_num_threads=1`. Concurrency across simultaneous sessions
still comes from `asyncio.to_thread` — each call gets its own OS thread — so this only bounds
*each session's own* internal thread pool, not overall parallelism across the process.

## Consequence

This was the actual root cause of the opening-line degradation observed in every live run,
not a genuine hardware/model-speed ceiling — CLAUDE.md's 1400ms e2e budget and the 400ms
per-chunk TTS deadline are achievable on this hardware once this is fixed. The holding-line
fallback added to `persona/opening.py` (Task 2.3f) stays regardless — a slow chunk is still a
real possibility (Groq hiccup, a genuinely long sentence, a loaded machine under real
concurrent-session load), and CLAUDE.md §6's degradation policy is "degrades before it dies,"
not "assume the fix means it can never happen again."

Not applied to Silero VAD's or faster-whisper's own onnxruntime/ctranslate2 sessions —
untouched, out of scope for this finding, and not implicated by the benchmark above (VAD/ASR
weren't degrading; this reproduced with a single isolated Piper voice and nothing else loaded).
If either is ever found to have the same symptom, it should get its own measured before/after,
not this fix applied by analogy.
