# 0023 — Two live-pipeline regressions found while recording the demo

**Context.** Recording `/demo` through the real realtime service was the first multi-turn live
session since Phase 5. Unit tests were green; the live pipeline was not.

1. **Every user turn failed to persist.** Phase 4's migration made `turns.training_excluded`
   NOT NULL and then dropped its server default. Realtime inserts through its own Core table,
   which never set the column, so each insert raised `NotNullViolationError` inside the turn task.
   The task died before the persona replied: the thinking watchdog fired, the session went
   degraded, and the user heard nothing. **Fix:** realtime writes `training_excluded=False`
   explicitly, and migration `b8c9d0e1f2a3` restores a server default of `false`. Regression test:
   `tests/integration/test_realtime_turn_insert.py`, confirmed red without the fix.
2. **The coach never scored live turns.** `WsTurnSink.enqueue_score_turn` existed and was unit
   tested, but nothing on the turn path called it. `generate_report` re-deferred itself forever,
   waiting for scores that were never requested. **Fix:** `process_turn` calls it right after the
   user turn and its metrics row are written. It remains fire-and-forget (a background task), so
   no latency is added. Verified live: the recorded demo session got 32 `turn_scores` rows and a
   ready report.

**Lesson.** Unit tests covered both pieces in isolation; nothing crossed realtime → Postgres →
Redis → coach. `scripts/record_demo.py` is now that end-to-end check.
