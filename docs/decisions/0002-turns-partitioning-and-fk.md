# 0002 — `turns` partitioning vs. foreign keys from its child tables

`docs/phase-0-BUILD.md` requires `turns` to be RANGE-partitioned by month on `created_at`, and
separately requires `turn_metrics`, `turn_scores`, `latency_events`, `model_calls` and
`annotations` to each carry `session_id` *and* `turn_id`, with FKs declaring `ondelete`
explicitly so that deleting a user cascades to zero orphans everywhere.

These two requirements are in tension in Postgres:

- A partitioned table's primary key **must include the partition key column**. So `turns`'
  PK is the composite `(id, created_at)`, not `id` alone.
- A foreign key from another table to a partitioned table must reference a unique constraint
  that **also** includes the partition key — i.e. every child table would need to carry its
  own duplicate `turn_created_at` column just to satisfy `FOREIGN KEY (turn_id, turn_created_at)
  REFERENCES turns(id, created_at)`.

## Decision

Child tables get a real, indexed, `ON DELETE CASCADE` foreign key to **`sessions.id`** (not
partitioned, no complication) and a **plain `turn_id` column with no DB-level FK** to `turns`.

This still satisfies the actual acceptance test — deleting a user cascades to zero orphans —
because the cascade path is `users → sessions → {turn_metrics, turn_scores, latency_events,
model_calls, annotations}` directly via `session_id`, not through `turns`. `turn_id` integrity
(a row always points at a real turn) is enforced by application code, which is the standard,
documented trade-off for this exact Postgres limitation — the alternative (denormalizing
`created_at` onto five child tables) buys referential integrity on a column that's already
transitively guaranteed correct by how the app writes these rows in the same transaction as
the turn.

## Why not skip partitioning instead

The spec is explicit that `turns` "grows fastest — partition by month from the start," and
that's the table an accepted job would generate the most rows in against realistic session
volume. Skipping it to sidestep the FK issue trades away the thing being tested for the thing
that's convenient.
