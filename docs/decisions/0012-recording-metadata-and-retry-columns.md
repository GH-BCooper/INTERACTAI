# 0012 — Recording metadata, waveform peaks, and retry-of columns live on `sessions`

**Phase:** 3, Task 3.3a/3.3f/3.4f.

## The decision

Three additions to the `sessions` table, all written by `services/realtime` at finalize (the
same place `close_session` already runs), never by `services/api`:

- `recording_key` (Text, nullable) / `recording_format` (Text, nullable, `wav`|`opus`) — the
  S3/MinIO object `services/api` mints a presigned GET URL against (`core/s3.py::presign_get_url`).
  `NULL` means no recording exists — either storage was never configured, or the session never
  captured any user audio — and the report UI must render that as "no recording," never an
  error.
- `peaks` (JSONB, nullable) — a ~1000-bucket waveform peaks array (Task 3.3a), computed once at
  finalize from the same PCM `finalize_recording` already has in memory before Opus-encoding it,
  so this costs nothing extra to obtain.
- `retry_of_session_id` (UUID, FK to `sessions.id`, `ON DELETE SET NULL`) / `retry_of_turn_id`
  (UUID, no FK — same reason `turn_metrics.turn_id`/`turn_scores.turn_id` have none: `turns` is
  partitioned, see 0002) — Task 3.4f's "retry one question" link back to the turn a short
  follow-up session re-asks.

## Why on `sessions`, not a new table

A new `session_recordings` table (1:1 with `sessions`) was the alternative. Rejected: every
consumer of this data (the report page's single `GET /sessions/{id}` and `GET
/sessions/{id}/recording` calls) already loads the session row anyway, and a 1:1 side table
buys normalization purity at the cost of an extra join on every read for data that is, in
practice, exactly as lifecycle-bound as the session itself — it's written once, at the same
moment, by the same code path that already updates `status`/`end_reason`/`duration_ms`.

## Why realtime writes it, not a background job

`finalize_recording` (`services/realtime/app/audio/upload.py`) already holds the decoded PCM
in memory to transcode it to Opus — computing peaks from that same buffer is a few lines, not a
new data-access path. A background job re-reading the object from S3 just to compute peaks would
duplicate work the finalize path already does for free, and would leave a window where a report
opened before the job runs shows no waveform at all.

## Why `recording_format` is a plain column, not derived from the key's extension

Because `services/api` (CLAUDE.md §2: "never touches audio") should never need to parse a
storage key to know how to label the format in `RecordingOut`. A denormalized column costs one
`CheckConstraint` and saves every reader a string-parsing assumption about key format that has
no reason to be load-bearing.
