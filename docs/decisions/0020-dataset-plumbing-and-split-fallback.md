# 0020 — `dataset_members` as its own table, and the <=2-speaker split fallback

**Context.** Task 5.1 lists three new tables (`model_versions`, `eval_runs`,
`dataset_revisions`) but Task 5.2's actual splitting logic needs to record, for one specific
build, which split and source each turn landed in. The task text doesn't name a table for this.

**Decision 1 — `dataset_members`.** A turn's split/source assignment is a property of *one
dataset revision*, not of the turn itself: rebuilding the dataset (e.g. once real labels exist
and stratification can finally use them, per Task 5.2c's own "stratify by criterion score
distribution") can legitimately reassign a turn to a different split under a new revision hash.
Storing split/source as columns on `turns` (the hot, partitioned, Phase-0-frozen table) would
make that impossible without a migration on the one table CLAUDE.md §5 asks to leave alone the
most. `dataset_members` is keyed by `(dataset_revision_hash, turn_id)` instead — cheap to
rebuild, trivial to garbage-collect old revisions, and it's exactly the shape `services/training/
dataset/build.py` and the admin annotation queue both need to query directly.

**Decision 2 — the <=2-speaker split fallback.** Task 5.2c's speaker-holdout rule is correct and
non-negotiable for a real dataset, but it degenerates when there are only one or two distinct
real speakers: the greedy bin-packing algorithm (fill test, then validation, from whole
speakers) would dump 100% of a single speaker's turns into one split, leaving the other two
splits empty. Since Phase 4's Day 17 recruited-session day never ran in this environment (see
docs/PHASE5-WALKTHROUGH.md), this degenerate case is not a hypothetical here — it is the actual
state of a fresh clone's real (non-synthetic, non-fixture) data.

`services/training/dataset/split.py::split_dataset` detects `len(speakers) <= 2` and falls back
to splitting by *session* instead of by speaker for that case only. This still cannot leak a
session across splits (verified directly in `tests/unit/training/test_dataset_split.py`), but it
no longer produces the true speaker-holdout guarantee the multi-speaker path gives — a real
speaker's turns can now appear in more than one split, exactly the "single most common
methodological error" the phase doc's own LEARN document warns about. This is an accepted,
disclosed tradeoff, not a silent one: `dataset_revisions.notes` and the console output from
`dataset/build.py` both report the count of distinct real speakers on every build, and Task 5.1's
own acceptance criteria treat "< 8 speakers" as a loud warning, not a passing state. The fallback
exists so the rest of the pipeline (annotation queue, training smoke-tests) has something to run
against at all while real multi-speaker data doesn't exist yet — it should stop engaging the
moment eight or more real speakers exist, which the same warning will make obvious.
