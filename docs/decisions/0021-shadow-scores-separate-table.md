# 0021 — Shadow mode writes to a new `shadow_scores` table, not `turn_scores`

**Context.** Task 5.5d's literal wording: "The prompted baseline runs alongside the fine-tune on
a sampled fraction (10%) of live turns, writing to `turn_scores` with its own `model_version`."

**The conflict.** `turn_scores` has been unique on `(turn_id, criterion_key)` — not `(turn_id,
criterion_key, model_version)` — since the Phase 0 migration. `services/coach/app/db/
repository.py::upsert_turn_score`'s own docstring already documents why this is deliberate and
load-bearing: "there is only ever one *current* score per turn+criterion by design (a rescore
with a new model_version should replace the old score, not coexist with it)." Every aggregation,
report, and evidence-display code path in `services/coach` and the report UI was built against
that invariant. Widening the constraint this late — specifically to let a second, non-primary
model_version coexist — would touch the one part of this schema every prior phase treated as
frozen (CLAUDE.md §5's "turn_metrics and turn_scores are separate tables and must stay separate"
spirit), for a feature (a comparison measurement) that was never meant to be user-visible in the
first place.

**Decision.** A new table, `shadow_scores`, unique on `(turn_id, criterion_key, model_version)` —
genuinely different from `turn_scores`'s identity, because the whole point of shadow mode is
that more than one model_version's opinion of the same turn+criterion coexists. Never read by
the report UI, never joined into aggregation, never shown to a user. `services/coach/app/report/
build.py::maybe_run_shadow_scoring` calls it after the primary `score_turn` path completes, with
its own scorer instance and its own failure isolation (a shadow-mode exception is caught and
logged, never allowed to fail the real scoring job).

**Consequence.** Comparing the shadow baseline against the primary scorer over time is a direct
query against `shadow_scores` joined to `turn_scores` on `(turn_id, criterion_key)` — trivial SQL,
and it can be built into `docs/RESULTS.md`'s generator once real shadow-mode data accumulates.
Nothing about the primary scoring path, `turn_scores`'s constraint, or any existing report code
needed to change.
