# 0003 — realtime reads/writes the DB through Core table mirrors, not api's ORM models

**Phase:** 1 (Task 1.1, 1.6a)

## The gap

`services/realtime` needs to read `sessions` (to validate a WS handshake) and write `turns`,
`turn_metrics`, `latency_events` and `model_calls` (Task 1.6a). Those tables and their ORM
classes already exist in `services/api/app/models/`. Nothing in CLAUDE.md or the Phase 0/1
specs says whether realtime may import that module directly.

## Decision

Realtime does not import `services.api.app.models`. It declares its own SQLAlchemy Core
`Table` objects in `services/realtime/app/db/tables.py`, hand-mirroring the exact columns it
touches, and reads/writes through plain `insert()`/`select()` statements in
`services/realtime/app/db/repository.py`.

## Why

- **Independent workspace members stay independent.** `services/api` and `services/realtime`
  are separate `pyproject.toml`s in the same uv workspace (CLAUDE.md §2) specifically so one
  can be redeployed, rewritten or removed without the other caring. Importing api's ORM
  classes from realtime would make realtime depend on api's SQLAlchemy declarative registry,
  its relationships, and indirectly its FastAPI app construction — none of which realtime
  needs, all of which now becomes something a change to api can break in realtime without
  either service's test suite noticing until runtime.
- **Alembic (api) remains the single owner of schema.** Core mirrors don't create tables or
  run migrations; they only describe columns for statement-building. The schema is still
  defined and evolved in exactly one place.
- **The cost is real and is accepted explicitly.** The two column lists (api's ORM, realtime's
  Core mirror) must be kept in sync by hand. `tests/integration` covers this: realtime's
  repository functions are exercised against the real, Alembic-migrated schema (the same
  testcontainers Postgres api's integration tests use), so a drift shows up as an insert
  failure in CI, not as a silent runtime surprise.

## Rejected alternative

A shared `packages/db-models` imported by both services. Rejected for now: it would need its
own versioning and release discipline for a two-consumer, same-repo, same-deploy-cadence
situation — overhead with no present payoff. Worth revisiting if a third service starts
needing the same tables.
