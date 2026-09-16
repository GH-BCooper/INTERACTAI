# 0022 — Level 1 / Level 2 evaluation suite design choices

**Context.** docs/phase-6-BUILD TASK 6.3 specifies the metrics but leaves how to measure several of
them open.

**Decisions.**
- **Only the RTF gates are hard failures in Level 1.** WER, endpoint precision and recall are
  reported but not gated: every fixture is Piper TTS, not recorded human speech, so any threshold
  set against it would be tuned to synthetic diction. A threshold belongs with a real-speech
  fixture set.
- **Endpoint precision/recall keep Phase 1's definitions** (`scripts/eval_endpointing.py`):
  recall = labelled boundaries where an end was called at all; precision = of those, called at or
  after the true end. The 220 labelled clips live in `data/boundaries/audio` (33 MB, not
  committed), so CI skips that part automatically; WER and RTF run from committed fixtures.
- **Time to first audio in Level 1 is read from `latency_events`** for the current `HOST_CLASS`,
  not re-simulated. It is only as representative as the sessions recorded on that host.
- **Persona character breaks = a judge label with a verified exact-substring quote, OR the
  deterministic post-check**, run on the text a user would actually hear (after the engine's
  regenerate/deflect step). Same "unverifiable evidence is discarded" rule as the coach.
- **Difficulty separation uses a one-sided Mann-Whitney U, gentle vs hard, p < 0.05 on each of the
  three measures separately.** Standard is run and reported but not part of the assertion.
- **Interruption is measured by the judge**, not by a word-count rule: `interrupt_over_words`
  exists only as a prompt instruction today; realtime has no code that interrupts on word count.
- **A persona reply that is still empty after one retry stands as the canned deflection** the
  engine substitutes, and is counted (`canned_deflections`). With `max_tokens=180` the reasoning
  model sometimes spends the whole budget before emitting content. That is real product
  behaviour, not an eval artefact.
- **The judge runs on `groq/openai/gpt-oss-120b`** (MODEL_JUDGE): a stronger model than the persona,
  with its own rate-limit bucket.
- **Question repetition uses `BAAI/bge-small-en-v1.5` embeddings** (MODEL_EMBEDDER), cosine ≥ 0.92
  within a session; plan adherence counts a topic covered at cosine ≥ 0.5 to any persona question.
  Both thresholds are uncalibrated first choices and should be revisited against labelled pairs.
