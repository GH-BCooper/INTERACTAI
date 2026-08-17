# Phase 0 — BUILD — Foundation (days 1–3)

Build specification for Claude Code. Read `CLAUDE.md` first.

**Exit criterion:** `make up && make migrate && make seed` succeeds from a clean clone; OAuth
sign-in works with GitHub and Google; `make schema` regenerates types for both languages;
three scenario families, four personas and two rubrics are seeded with complete anchor
descriptors.

**Rule for this phase:** one task per session. Do not implement ahead.

---

## TASK 0.1 — Monorepo skeleton and tooling

### Create

```
interactai/
├── CLAUDE.md                    (already present — do not overwrite)
├── .gitignore .env.example .editorconfig
├── Makefile  docker-compose.yml  pnpm-workspace.yaml  package.json
├── packages/schema/
├── services/{api,realtime,coach,training}/
├── apps/web/
├── content/{scenarios,personas,rubrics,prompts}/
├── models/     (gitignored)
├── docs/       (specs live here)
├── scripts/
└── tests/{fixtures,unit,integration,safety}/
```

### Requirements

- **Python dependency management is `uv` only.** Each Python service has its own
  `pyproject.toml` and shares one root `uv.lock` via a workspace. `requires-python = "==3.11.*"`.
- **JS dependency management is `pnpm` only,** with a workspace covering `apps/web` and
  `packages/schema`.
- `.gitignore` must include: `.env`, `models/`, `*.wav`, `*.pcm`, `*.opus`, `__pycache__/`,
  `.venv/`, `node_modules/`, `.next/`, `kaggle.json`, `wandb/`, `data/raw/`.
- Ruff config at root: line-length 100, target py311, rules `E,F,I,N,UP,B,ASYNC,S`.
  `mypy --strict` configured for `services/realtime` only.
- `.editorconfig`: LF, UTF-8, 4-space Python, 2-space TS/YAML/JSON.

### Makefile targets (exact names — other docs reference them)

`up down logs migrate makemigration seed api realtime coach web schema test lint fmt cli eval clean`

Each target must work from a clean clone after `.env` is created. `make up` must be idempotent.

### Acceptance criteria

- [ ] `uv sync` succeeds at the root and resolves all four Python services
- [ ] `pnpm install` succeeds and links the workspace
- [ ] `make lint` passes on the empty skeleton
- [ ] `git status` is clean after a full install (nothing generated is untracked)
- [ ] No file in the repo contains a real secret

---

## TASK 0.2 — Docker Compose infrastructure

### Services

| Service | Image | Host port | Volume |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | 5432 | `pgdata` |
| `redis` | `redis:7-alpine` | 6379 | `redisdata` |
| `minio` | `minio/minio` | 9000 (API), 9001 (console) | `miniodata` |
| `minio-init` | `minio/mc` | — | one-shot bucket creation |

### Requirements

- Postgres init script creates the database and runs `CREATE EXTENSION IF NOT EXISTS vector;`
  and `CREATE EXTENSION IF NOT EXISTS "uuid-ossp";`
- **Every service has a healthcheck.** `postgres` uses `pg_isready`, `redis` uses `redis-cli
  ping`, `minio` uses `curl -f http://localhost:9000/minio/health/live`.
- `minio-init` runs after minio is healthy, creates bucket `interactai-audio` (private) and
  exits 0. It must be idempotent — re-running `make up` must not error on an existing bucket.
- Named volumes, not bind mounts, for data. `make clean` removes them; nothing else does.
- All services on one user-defined network named `interactai`.
- **Do not containerise `api`, `realtime`, `coach` or `web` for local development.** They run
  on the host with hot reload. Production Dockerfiles come in Phase 6.

### Edge cases to handle

- Port already in use → the compose file must make host ports overridable via env
  (`POSTGRES_HOST_PORT=${POSTGRES_HOST_PORT:-5432}`).
- Stale volume with an old schema → `make clean` must actually remove volumes, and must
  require confirmation before doing so.
- MinIO on ARM (Apple Silicon) → do not pin a platform; let Docker resolve it.

### Acceptance criteria

- [ ] `make up` from a clean state reaches all-healthy within 30 s
- [ ] `make up` run twice in a row succeeds both times
- [ ] `psql` from the host connects and `SELECT * FROM pg_extension` lists `vector`
- [ ] MinIO console at `localhost:9001` shows an empty `interactai-audio` bucket
- [ ] `make down` stops everything and preserves data; `make clean` removes it after confirmation

---

## TASK 0.3 — Shared schema package and code generation

This is the contract between Python and TypeScript. Build it before anything that uses it.

### Create `packages/schema/ws-messages.schema.json`

A JSON Schema (draft 2020-12) defining a **discriminated union** on the `type` field, covering
every WebSocket message. Include all of the following now, even though most are not implemented
until Phase 1 — adding message types later is a versioned change.

**Client → server (JSON control frames):**

| type | Fields |
|---|---|
| `hello` | `protocol_version`, `session_id`, `client_sample_rate`, `client_frame_ms`, `capabilities[]` |
| `resume` | `protocol_version`, `session_id`, `last_server_seq`, `last_client_seq` |
| `mute` | `muted: bool` |
| `end_session` | `reason: "user_hangup" \| "user_abandoned"` |
| `ping` | `client_time_ms` |

**Server → client (JSON control frames):**

| type | Fields |
|---|---|
| `ready` | `session_id`, `server_sample_rate`, `protocol_version`, `resumed: bool` |
| `state_change` | `state` (the 8 machine states), `client_state` (the 4 user-visible states), `at_ms` |
| `partial_transcript` | `turn_index`, `text`, `stability: float`, `at_ms` |
| `turn_finalized` | `turn_id`, `turn_index`, `text`, `start_ms`, `end_ms`, `asr_confidence`, `word_timings[]` |
| `persona_text` | `turn_id`, `text_delta`, `done: bool` |
| `audio_chunk_meta` | `turn_id`, `chunk_seq`, `sample_rate`, `byte_length`, `is_final` |
| `interrupted` | `turn_id`, `at_ms`, `truncated_text` |
| `degraded` | `component: "asr"\|"tts"\|"persona"\|"transport"`, `message`, `recoverable: bool` |
| `latency_report` | `turn_id`, `stages: {stage, duration_ms}[]`, `e2e_ms` |
| `session_closed` | `reason`, `duration_ms`, `report_pending: bool` |
| `error` | `code`, `message`, `recovery`, `fatal: bool`, `trace_id` |
| `pong` | `client_time_ms`, `server_time_ms` |

**Binary frames carry no JSON.** They are documented in Task 0.4's protocol doc and use a
fixed 12-byte header (see `docs/03-realtime-protocol.md`).

### Requirements

- Every message includes `type` (const string) and `seq` (monotonic uint32 per direction).
- `protocol_version` is a string, currently `"1.0"`. A `hello` with a mismatched major version
  gets an `error` with code `ORCHESTRATION_PROTOCOL_MISMATCH` and `fatal: true`.
- `additionalProperties: false` on every message object. Silent extra fields are exactly how
  drift starts.
- `generate.py` uses `datamodel-code-generator` → `services/*/app/schemas/ws.py` with a
  discriminated-union `RootModel` and `Literal` types.
- `generate.ts` uses `json-schema-to-typescript` → `apps/web/lib/ws-types.ts`, plus a hand-
  maintained `assertNever` helper for exhaustive switches.
- Generated files carry a `# GENERATED — DO NOT EDIT. Run make schema.` header.

### Acceptance criteria

- [ ] `make schema` produces both outputs deterministically (running twice gives identical bytes)
- [ ] A Python test round-trips one instance of **every** message type through Pydantic
- [ ] A vitest test type-checks one instance of every message type
- [ ] A CI step regenerates and fails if the working tree differs
- [ ] Adding an unknown field to a message fails validation on the Python side

---

## TASK 0.4 — Database schema and migrations

Implement all 15 P0 tables per `docs/02-data-model.md`.

### Tables

`users` · `profiles` · `personas` · `scenarios` · `rubrics` · `rubric_criteria` · `sessions` ·
`turns` · `turn_metrics` · `turn_scores` · `session_scores` · `reports` · `latency_events` ·
`model_calls` · `annotations`

**Do not create** `scenario_versions`, `model_versions` or `eval_runs` yet — those arrive on
day 18. Do not add them speculatively.

### Universal requirements

- `id UUID PRIMARY KEY` using **UUID v7** (`uuid_utils.uuid7`), `created_at`, `updated_at`,
  all timezone-aware UTC, `server_default=func.now()`.
- Foreign keys declare `ondelete` explicitly. User deletion cascades to everything owned by
  that user — this is required by AS-05 (one-click data deletion) and cannot be bolted on.
- `turns` is **partitioned by month** on `created_at` (declarative partitioning; create the
  current and next month's partitions in the migration, plus a helper in `scripts/`).

### Column notes that must not be lost

| Table | Note |
|---|---|
| `profiles` | `resume_text` is nullable and independently deletable without deleting the profile |
| `personas` | `archetype ∈ {interviewer, hiring_manager, recruiter, examiner, skeptic}`; `temperament ∈ {warm, neutral, blunt, adversarial}` |
| `scenarios` | `family ∈ {technical, behavioural, negotiation, viva}`; `difficulty ∈ {gentle, standard, hard}` |
| `rubric_criteria` | `anchor_descriptors JSONB` — map from score value (string) to written definition. **Required, non-empty, one entry per point on the scale.** Enforce with a CHECK or a validator. |
| `sessions` | `status ∈ {created, active, closing, closed, failed}`; `end_reason ∈ {user_hangup, duration_reached, persona_concluded, budget_exhausted, distress_exit, error}` |
| `turns` | `speaker ∈ {user, persona}`; `word_timings JSONB`; `truncated BOOL`; unique `(session_id, index)` |
| `turn_metrics` | deterministic only: `wpm, filler_count, filler_rate, longest_pause_ms, speech_ratio, word_count`. **No model ever writes here.** |
| `turn_scores` | `evidence_spans JSONB` = list of `{start, end}` char offsets into `turns.text`; `confidence FLOAT`; `model_version TEXT` |
| `latency_events` | `stage` is a constrained enum (see CLAUDE.md §8). Index on `(session_id, turn_id, stage)` and on `(stage, created_at)` for percentile queries. |
| `model_calls` | `cached BOOL`, `ttft_ms`, `cost_cents NUMERIC(10,6)`. Written for **every** invocation, no sampling. |
| `annotations` | `round INT NOT NULL DEFAULT 1`; unique `(turn_id, annotator_id, criterion_key, round)` |

### Indexes required

```
sessions(user_id, created_at DESC)
turns(session_id, index)
turn_scores(turn_id, criterion_key)
latency_events(session_id, turn_id)
latency_events(stage, created_at DESC)
model_calls(session_id, created_at)
annotations(turn_id, criterion_key)
scenarios USING ivfflat (embedding vector_cosine_ops)   -- pgvector, added when embeddings land
```

### Acceptance criteria

- [ ] `make migrate` from empty succeeds; `alembic downgrade base` then `upgrade head` also succeeds
- [ ] All FK cascades verified by a test that deletes a user and asserts zero orphans across all tables
- [ ] A test asserts `rubric_criteria` rejects an empty or partial `anchor_descriptors`
- [ ] A test asserts `turns` rejects a duplicate `(session_id, index)`
- [ ] Inserting 1,000 turns and selecting the last 20 by index uses the index (check `EXPLAIN`)
- [ ] Migration file is hand-reviewed, not blind autogenerate — indexes are present in it

---

## TASK 0.5 — API service: auth and core CRUD

FastAPI at port 8000. **Stateless. Never touches audio.**

### Endpoints

```
GET    /health                          liveness — no DB
GET    /health/ready                    readiness — checks DB, Redis, S3
GET    /auth/{provider}/login           provider ∈ {github, google}
GET    /auth/{provider}/callback        → sets refresh cookie, returns access token
POST   /auth/refresh                    rotating refresh
POST   /auth/logout                     revokes the refresh family
GET    /me
PATCH  /me/profile
DELETE /me                              AS-05: full deletion incl. object storage
GET    /scenarios                       filter: family, difficulty, duration, tag
GET    /scenarios/{id}
POST   /scenarios                       P1 — stub returning 501 for now
GET    /personas
GET    /rubrics
GET    /rubrics/{id}
POST   /sessions                        creates the session + compiles the brief
GET    /sessions                        paginated history
GET    /sessions/{id}
POST   /sessions/{id}/ws-token          mints the short-lived socket credential
GET    /sessions/{id}/report            404 until the coach has written it
```

### Auth requirements

- Authlib for both providers. **Two separate OAuth apps per provider** (dev and prod) — read
  client id/secret from env, never hardcode.
- Access JWT: 15 min, HS256, `JWT_SECRET`, claims `sub`, `scopes`, `exp`, `iat`, `jti`.
- Refresh token: 30 days, **rotating**. Stored hashed in Redis keyed by family id. On reuse of
  a rotated token, revoke the entire family and return 401 — that is theft, not a race.
- Cookie flags: `httpOnly`, `secure` (except when `ENVIRONMENT=development`), `SameSite=Lax`,
  `Path=/auth`.
- CSRF: OAuth `state` parameter, stored in Redis with a 10-minute TTL, single use.

### WS token requirements (`POST /sessions/{id}/ws-token`)

- Signed with `WS_TOKEN_SECRET` — **must not be `JWT_SECRET`**. Assert this at startup and
  refuse to boot if they are equal.
- TTL 120 s. Claims: `session_id`, `user_id`, `jti`, `exp`.
- **Single use.** `jti` is written to Redis with the token's TTL on mint and deleted on first
  successful upgrade. A second use returns `ORCHESTRATION_TOKEN_REUSED`.
- Only the session owner may mint one, and only for a session in status `created` or `active`.

### Session creation requirements

`POST /sessions` body: `scenario_id`, `difficulty`, `target_minutes ∈ {5,10,20,30}`,
optional `focus_areas[]`, optional `resume_text_override`.

It must **compile and freeze a session brief** — resolved persona prompt reference, opening
strategy, rubric id, difficulty parameters and budget caps — stored as JSONB on the session
row. The brief is immutable for the session's lifetime. This is what makes a run reproducible
and comparable to the user's previous attempt.

### Error handling

Every error response uses the shape in `CLAUDE.md` §6. Specifically required codes here:
`AUTH_INVALID_TOKEN`, `AUTH_TOKEN_REUSED`, `AUTH_PROVIDER_ERROR`, `NOT_FOUND`, `FORBIDDEN`,
`VALIDATION_ERROR`, `RATE_LIMITED`, `ORCHESTRATION_TOKEN_REUSED`.

### Rate limits (AS-10)

- 30 requests/min per IP on auth endpoints
- 10 sessions/hour and 40 sessions/day per user
- `MAX_CONCURRENT_SESSIONS` (default 4) enforced at session creation

### Acceptance criteria

- [ ] Full OAuth round trip works for GitHub **and** Google against real providers
- [ ] Refresh rotation works; presenting a rotated token revokes the family (test asserts this)
- [ ] API refuses to start if `JWT_SECRET == WS_TOKEN_SECRET`
- [ ] WS token: valid once, rejected the second time, rejected after 120 s, rejected for a
      different user's session
- [ ] `DELETE /me` removes all rows across all 15 tables and purges the S3 prefix; a test
      asserts zero remaining rows and zero remaining objects
- [ ] `GET /health/ready` returns 503 when Postgres is stopped
- [ ] Every endpoint has a Pydantic response model; `/docs` renders without warnings
- [ ] Rate limits return 429 with `Retry-After`

---

## TASK 0.6 — Content authoring and seeding

**This is content work, not code work, and it blocks Phase 5.** Quality here directly
determines inter-annotator agreement on day 19.

### Deliverables

**Three scenario families**, each with one fully authored scenario at each of three
difficulties (9 scenarios total):
1. `technical` — backend engineer, system design screen
2. `behavioural` — behavioural / STAR screen
3. `negotiation` — salary negotiation after a lowball offer

*(A fourth, `viva`, is P1 — do not author it now.)*

**Four personas** with genuinely distinct temperaments (`warm`, `neutral`, `blunt`,
`adversarial`), each with a fixed `voice_id` from the downloaded Piper voices.

**Two rubrics**: `general_interview` (structure, specificity, relevance, concision,
confidence, technical_depth, tradeoff_reasoning) and `negotiation` (structure, specificity,
relevance, concision, confidence, anchoring, justification, concession_discipline).

### Format

YAML in `content/{scenarios,personas,rubrics}/`. Seeded by `make seed`, which must be
**idempotent** — re-running updates in place by a stable `slug`, never duplicating.

### Scenario brief requirements

A brief must specify: who the persona is, where they are, what they care about, what
unimpresses them, their time constraint, and their opening strategy. Generic briefs produce
generic personas. Example of the required level of specificity:

```yaml
brief: |
  You are a staff engineer at a mid-size fintech, forty minutes into a day of
  back-to-back screens and slightly behind schedule. You have read the candidate's
  resume once. You care about whether they have actually operated a system in
  production; you are unimpressed by framework name-dropping. You have a hard stop
  in twenty minutes and you will say so if the candidate rambles.
opening_strategy: |
  Open with a brief thanks, then immediately ask them to walk you through the
  hardest thing they shipped this year. Do not explain the format.
```

### Rubric anchor requirements — enforced

Every criterion must have an anchor descriptor for **every point 1–5**. Each descriptor must
name something **observable in the transcript**, not a quality judgement. Reject any
descriptor that is a bare adjective phrase ("good structure", "adequate detail").

Write a validator in `scripts/validate_content.py` that fails the seed if:
- any criterion is missing any scale point,
- any descriptor is under 40 characters,
- any descriptor matches `^(very )?(good|bad|poor|excellent|adequate|fine)\b`,
- any scenario brief is under 200 characters,
- any persona lacks a `voice_id` that exists in `models/piper/`.

### Difficulty must change behaviour, not wording

Store per-tier behavioural parameters on the scenario, not just harder questions:

```yaml
difficulty_params:
  gentle:   { followups_on_vague: 0, hint_after_pause_ms: 4000, interrupt: false,
              ack_length: long,  silence_after_answer_ms: 0 }
  standard: { followups_on_vague: 1, hint_after_pause_ms: null, interrupt: false,
              ack_length: short, silence_after_answer_ms: 0 }
  hard:     { followups_on_vague: 3, hint_after_pause_ms: null, interrupt: true,
              ack_length: minimal, silence_after_answer_ms: 1500,
              challenge_claims: true, time_pressure: true }
```

A persona that asks harder questions in the same friendly manner is not harder practice.

### Acceptance criteria

- [ ] 9 scenarios, 4 personas, 2 rubrics seeded
- [ ] `make seed` is idempotent — running it three times leaves the row counts unchanged
- [ ] `scripts/validate_content.py` passes and **fails loudly** on a deliberately broken fixture
- [ ] Every rubric criterion has 5 anchor descriptors, each ≥ 40 chars and observable
- [ ] Every persona's `voice_id` resolves to a file in `models/piper/`
- [ ] `GET /scenarios` returns all 9 with correct filtering by family and difficulty

---

## TASK 0.7 — Test harness and CI

### Setup

- `pytest` + `pytest-asyncio` + `testcontainers` (Postgres and Redis for integration tests).
- `vitest` for the web workspace.
- Fixtures: `db_session` (transactional, rolled back per test), `seeded_content`,
  `authed_client`.
- **A committed audio fixture directory** `tests/fixtures/audio/` with at least: a 3-second
  clean utterance, a 3-second utterance with a 700 ms mid-sentence pause, an accented
  utterance, and 2 seconds of silence. Record these yourself now — Phase 1 needs them and
  recording them mid-debug is miserable.

### CI (`.github/workflows/ci.yml`)

Jobs: `lint` (ruff + mypy + eslint + tsc) · `schema-drift` (regenerate, fail on diff) ·
`test-python` · `test-web` · `content-validate`.

CI must fail on: lint errors, type errors, schema drift, any failing test, and any content
validation failure.

### Acceptance criteria

- [ ] `make test` runs both suites and passes
- [ ] Integration tests spin up real Postgres and Redis, not mocks
- [ ] CI passes on a fresh push
- [ ] Deliberately breaking the JSON Schema without regenerating fails the `schema-drift` job

---

## Phase 0 definition of done

- [ ] Clean clone → `.env` → `make up && make migrate && make seed` works with no manual steps
- [ ] OAuth sign-in works for both providers
- [ ] WS token minting is single-use, scoped and short-lived
- [ ] All 15 tables migrated with the required indexes and cascades
- [ ] One JSON Schema generates both Pydantic and TypeScript, verified by round-trip tests
- [ ] 9 scenarios / 4 personas / 2 rubrics seeded and validated
- [ ] `DELETE /me` genuinely removes everything including S3 objects
- [ ] CI green

**Do not start Phase 1 until every box above is ticked.** The audio work assumes all of this
is solid, and debugging a migration while also debugging a streaming decoder is how days
disappear.
