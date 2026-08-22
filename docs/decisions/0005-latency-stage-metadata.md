# 0005 — stage metadata (e.g. ASR's RTF) goes to a log line, not the `latency_events` table

**Phase:** 1 (Task 1.6a, in tension with Task 1.4)

## The gap

Task 1.6a's `stage()` context manager signature takes `**metadata`. Task 1.4 says: "Measure
RTF on every final pass and write it to `latency_events` as stage `asr_finalize` alongside a
`metadata.rtf` value." But the `latency_events` table, as built in Phase 0
(`services/api/app/models/observability.py`), is exactly four columns:
`session_id, turn_id, stage, duration_ms`. There is no metadata/JSONB column.

## Decision

`stage()` still accepts `**metadata`, but it never reaches the DB row. The row written to
`latency_events` is always the bare four columns. When metadata is present, `stage()` emits a
structured log line (`latency_stage_metadata`) carrying the same `session_id`/`turn_id`/`stage`
plus whatever metadata was passed (e.g. `rtf=0.42`).

## Why

- **Not a schema change.** `latency_events` is Phase-0-frozen application schema, migrated via
  Alembic and hand-reviewed (CLAUDE.md §5). Widening it to carry a JSONB metadata column is a
  real migration decision — worth doing, but not something to do unilaterally as a side effect
  of Task 1.4's TTFT/RTF instrumentation wording.
- **The distinction CLAUDE.md §5 draws is about the duration, not about every fact adjacent to
  it.** "A table, not a log line" argues that the *headline number* (how long did this stage
  take) must be queryable with p50/p95, not grepped. RTF is diagnostic context for *why* a
  stage was slow, not the timing claim itself — a log line is the right home for it, same as
  any other structured diagnostic detail.
- **Every model invocation still gets its own real table row.** `model_calls`
  (`services/realtime/app/metrics/model_calls.py`) already has dedicated columns for
  `tokens_in`, `tokens_out`, `ttft_ms`, `total_latency_ms`, `cost_cents`, `cached` — the
  *model-call-shaped* metadata Task 1.6a actually asks to be tabular. RTF is ASR-specific and
  doesn't fit that shape either.

## If this needs to change

If a future phase wants RTF (or other per-stage metadata) queryable in aggregate rather than
grepped from logs, the honest fix is a migration adding a nullable `metadata JSONB` column to
`latency_events`, not routing it through `model_calls` or inventing a second table.
