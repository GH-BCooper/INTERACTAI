# Phase 0 — LEARN — Foundation (days 1–3)

**Exit criterion:** the stack runs locally in one command, the schema is migrated, and
scenarios, personas and rubrics are authored and seeded.

**Study time this phase:** ~6 hours (Docker/Compose 3h, SQLAlchemy 2.0 3h).
**Heavy technologies today:** none. This is deliberate — you are building the surface the
hard parts land on.

---

## Why this phase exists

You are about to spend five days inside a Python process that must do VAD, ASR, LLM and TTS
streaming inside 1.5 seconds. Every hour of that week that you spend fighting a migration, a
container network, or a type mismatch between your frontend and backend is an hour stolen from
the only part of this project that is actually hard.

Phase 0 is insurance. It is also the phase most people rush, and then pay for on day 11.

There is a second, less obvious reason. **Day 3 is content authoring, and it blocks Phase 5.**
The rubric anchor descriptors you write on day 3 are read by three different consumers: the
human annotator on day 19, the model you train on day 20, and the user reading their report.
If those words are vague, your inter-annotator agreement on day 19 will be 0.4, and a model
trained against a 0.4 ceiling is not worth training. **You cannot fix that on day 19.** Write
them properly now.

---

## 1. Why one backend language

The honest version of this trade-off matters, because you will be asked it.

A dual-runtime split — TypeScript for the API, Python for the AI workers — is defensible and
extremely common. It is rejected here for one specific reason: **this project's difficulty is
concentrated in a single Python process** that must do VAD, ASR streaming, LLM streaming and
TTS streaming inside a 1.5 second budget.

Adding a language boundary on that path buys nothing and costs:
- a serialisation hop (you would be shipping PCM frames across a process boundary),
- a second dependency tree and a second set of Docker layers,
- and hours of cross-runtime debugging that belong in the latency budget instead.

The front end stays TypeScript because the browser gives you no choice. The contract between
them is **one versioned WebSocket message schema, generated from a single JSON Schema into
both Pydantic models and TypeScript types**, so they cannot silently drift.

That last sentence is the actual engineering idea, and it is what you build on day 1.

---

## 2. The four services, and what "stateful" actually means

| Service | Language | Responsibility | Stateful? |
|---|---|---|---|
| `web` | TypeScript | Next.js. Server components for history and reports; the practice room is a client island owning capture, the worklet, the socket and playback. | No |
| `api` | Python | FastAPI. Auth, scenario/rubric CRUD, session creation, report retrieval, analytics. **Never touches audio.** | No |
| `realtime` | Python | The latency-critical service. One WebSocket per session, turn state machine, VAD, endpointing, ASR streaming, persona call, synthesis streaming. | **Yes** |
| `coach` | Python | Off-path worker. Consumes completed turns from a queue, runs the scorer and the narrative model, writes scores and the report. Its slowness is invisible. | No |

Plus three managed dependencies: **Postgres** (with pgvector, so you avoid a second
database), **Redis** (ARQ queue, report-ready pub/sub, ephemeral session state, rate limits),
and **S3-compatible object storage** (audio segments, recordings, report assets).

### The thing worth understanding

`realtime` is stateful in a way that has real consequences. A session is **pinned to one
process for its lifetime**, because that process holds:

- an open WebSocket,
- a growing audio ring buffer,
- a resident ASR model (~150 MB) with in-flight decoder state,
- the turn state machine's current state,
- the persona's compacted conversation history and question plan.

None of that can move to another process mid-session. This is why the realtime service
**cannot be serverless**, cannot sit behind a naive round-robin load balancer, and needs a
"resume" path rather than a "retry" path when the socket drops.

If you can explain that paragraph in an interview, you have already demonstrated more systems
thinking than most portfolio projects contain.

---

## 3. Docker Compose — the three things that matter

You have Docker basics. The increment here is three specific things.

### 3.1 Service names are DNS names

Inside the Compose network, `postgres` resolves to the Postgres container. From your host, it
does not — you need `localhost:5432` and a published port. This is the source of the most
common Compose confusion:

```yaml
services:
  postgres:
    ports:
      - "5432:5432"   #  host:container
```

- Code **running inside Compose** connects to `postgres:5432`.
- Code **running on your host** (which is how you will run `api` and `realtime` in dev, for
  fast reload) connects to `localhost:5432`.

Keep two env values or make the host configurable. Do not fight this — it is by design.

### 3.2 `depends_on` does not mean "ready"

`depends_on` waits for the container to *start*, not for Postgres to accept connections. Your
migration will fail with "connection refused" roughly one time in three. The fix is a
healthcheck plus `condition: service_healthy`:

```yaml
postgres:
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U interactai"]
    interval: 3s
    timeout: 3s
    retries: 10
api:
  depends_on:
    postgres:
      condition: service_healthy
```

### 3.3 Multi-stage builds, and why model images are enormous

A naive Python image for `realtime` is ~4 GB: build toolchain, pip cache, PyTorch pulled in as
a transitive dep, model weights baked in. That is slow to build, slow to push, and slow to
cold-start on Hugging Face Spaces.

Three fixes, in order of impact:

1. **Multi-stage.** Build deps in a builder stage, copy only the resulting virtualenv into a
   slim runtime stage.
2. **Mount weights, don't bake them.** `models/` is a volume in dev and a startup download in
   prod. Baking a 150 MB Whisper model into a layer means re-pushing it on every code change.
3. **Order layers by change frequency.** Copy `pyproject.toml` + `uv.lock` and install
   *before* copying source. Then a code change invalidates one cheap layer instead of the
   whole dependency install.

```dockerfile
FROM python:3.11-slim AS builder
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev          # ← cached until deps change

FROM python:3.11-slim AS runtime
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY ./app /app/app                     # ← the only layer that churns
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Skip Kubernetes entirely.** It is not in scope and it will eat a week.

---

## 4. SQLAlchemy 2.0 — what actually changed

You know PostgreSQL and schema design; this is just the ORM idiom. Three things to internalise
and one whole API to ignore.

### 4.1 Declarative models with `Mapped[]`

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase): ...

class Session(Base):
    __tablename__ = "sessions"
    id:          Mapped[UUID]     = mapped_column(primary_key=True, default=uuid7)
    user_id:     Mapped[UUID]     = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status:      Mapped[str]      = mapped_column(String(24), default="created")
    ended_at:    Mapped[datetime | None]                      # nullable inferred from the type
    turns:       Mapped[list["Turn"]] = relationship(back_populates="session")
```

The `Mapped[...]` annotation is not decoration — mypy reads it, and nullability comes from
`| None` rather than a separate `nullable=` argument.

### 4.2 `select()`, not `query()`

```python
# 2.0 style — the only style you should write
result = await session.execute(
    select(Session).where(Session.user_id == uid).order_by(Session.created_at.desc()).limit(10)
)
sessions = result.scalars().all()
```

The legacy `session.query(...)` API still works and every Stack Overflow answer from before
2023 uses it. **Skip it entirely.** Mixing the two is how you end up with confusing errors.

### 4.3 Async sessions and the lazy-loading trap

This will bite you, so learn it now rather than at 1 a.m. on day 14.

```python
# ❌ this raises MissingGreenlet in async
session = await db.get(Session, sid)
print(session.turns)          # lazy load → implicit IO → boom in async context

# ✅ load explicitly
result = await db.execute(
    select(Session).options(selectinload(Session.turns)).where(Session.id == sid)
)
```

In async SQLAlchemy, **lazy loading is not available.** Every relationship you intend to
traverse must be loaded eagerly with `selectinload` (separate query, good for collections) or
`joinedload` (a JOIN, good for many-to-one). If you see `MissingGreenlet`, you forgot one.

### 4.4 Alembic in one paragraph

`alembic revision --autogenerate -m "..."` diffs your models against the database and writes a
migration. **Always read it before applying.** Autogenerate reliably misses: index changes,
server defaults, enum value additions, and anything involving a type change with data in it.
For this project the schema is fixed on day 1, so you should have roughly four migrations
total across 24 days.

---

## 5. UUID v7 — a small decision that pays daily

UUID v4 is random. Rows inserted in time order land in random positions in the B-tree index,
which fragments the index and — more importantly for you — means `ORDER BY id` is meaningless.

UUID v7 embeds a millisecond timestamp in the high bits. So:

- primary keys sort by creation time,
- index inserts are append-mostly, so `turns` (which grows fastest) stays clustered,
- and when you are staring at three UUIDs in a log line on day 11, you can tell which happened
  first without joining anything.

That last benefit sounds trivial. It is not, when you are debugging a latency waterfall.

```python
from uuid_utils import uuid7   # or uuid6 package; either is fine
```

---

## 6. One schema, two languages — the codegen idea

This is the highest-leverage thing you build on day 1 and it takes about ninety minutes.

**The problem it solves:** you will define ~15 WebSocket message types. The Python side
validates them with Pydantic. The TypeScript side needs matching types. If those are written
by hand in two places, they *will* drift — usually silently, usually in a field you added on
day 9 and forgot to mirror, usually discovered on day 13 when the practice room renders
`undefined`.

**The solution:** one JSON Schema file is the source of truth.

```
packages/schema/ws-messages.schema.json
        │
        ├── generate.py  → datamodel-code-generator → services/*/app/schemas/ws.py  (Pydantic)
        └── generate.ts  → json-schema-to-typescript → apps/web/lib/ws-types.ts     (TS)
```

Run `make schema` after any change. Add a CI check that regenerates and fails if the output
differs from what is committed — that turns "someone forgot to regenerate" from a day-13
mystery into a red build.

**Design the messages as a discriminated union** on a `type` field. That gives you exhaustive
`switch` handling in TypeScript with compile-time completeness checking:

```ts
switch (msg.type) {
  case "partial_transcript": ...; break;
  case "turn_finalized":     ...; break;
  // if you add a message type and forget a case, tsc tells you
  default: assertNever(msg);
}
```

---

## 7. Auth: three different tokens, on purpose

| Token | Lifetime | Carries | Where it lives |
|---|---|---|---|
| Access JWT | 15 min | user id, scopes | `Authorization` header |
| Refresh token | 30 days, rotating | session id | httpOnly, secure, SameSite=Lax cookie |
| **WS session token** | **2 min, single use** | session id + user id, scoped to one practice session | query string on the socket URL |

You already know JWT and refresh rotation. The new piece is the third one, and the reason for
it is specific:

**A WebSocket handshake cannot carry a custom `Authorization` header from browser JS.** The
browser `WebSocket` constructor accepts a URL and a subprotocol list, and nothing else. So the
credential has to travel in the URL — and URLs land in proxy logs, browser history, and
`Referer` headers.

Therefore the WS token is: minted by the API right before connecting, valid for two minutes,
scoped to exactly one session id, single-use (burned in Redis on first successful upgrade),
and signed with `WS_TOKEN_SECRET` — a **different secret** from your session JWT. A leaked WS
token then costs you exactly one practice session, not an account.

The rotation rule for refresh tokens: on every refresh, issue a new refresh token and
invalidate the old one. If an old one is ever presented again, that is theft — revoke the whole
family.

---

## 8. Writing rubric anchors — the highest-value hour in the project

Day 3 looks like the easy day. It is the one that decides whether Phase 5 produces a number
worth publishing.

### What an anchor descriptor is

Each rubric criterion has a written definition for **every point on the five-point scale**.
Those exact words are read by three consumers:

1. the human annotator on day 19, deciding between a 3 and a 4,
2. the model on day 20, which is trained against those labels,
3. the user on day 15, reading why they got a 3.

One set of words, three consumers. This is why writing them carefully matters more than any
hyperparameter you will choose later.

### Bad anchors vs good anchors

❌ **Bad — unfalsifiable, no observable referent:**
```
5: Excellent structure
4: Good structure
3: Adequate structure
2: Poor structure
1: Very poor structure
```
Two annotators will disagree constantly, your ceiling will land near 0.4, and the model will
learn noise.

✅ **Good — every level names something you can point at in the transcript:**
```
structure — Does the answer have a discernible arc rather than a stream of facts?

5  Opens by naming the situation, moves through action to outcome, and closes by
   returning to the question asked. A listener could summarise it in one sentence.
4  A clear arc with one weak transition or a missing close. Still easy to follow.
3  Recognisable beginning and end, but the middle wanders or the order has to be
   reconstructed by the listener.
2  Facts in the order they occurred to the speaker. No signposting. A listener would
   need to ask "so what happened in the end?"
1  No discernible organisation. The answer starts mid-thought or never resolves.
```

Every level names something **observable**. "A listener could summarise it in one sentence" is
a test. "Good structure" is a feeling.

### The five universal criteria

`structure` · `specificity` · `relevance` · `concision` · `confidence`

Plus, by family:
- **technical, viva:** `technical_depth`, `tradeoff_reasoning`
- **negotiation:** `anchoring`, `justification`, `concession_discipline`

### The test to apply before you move on

Take three real answers you have given in your life — one good, one mediocre, one bad. Score
them against your own anchors. If you hesitate for more than a few seconds on any of them, the
anchor is too vague. **Rewrite it now.** On day 19 you will be doing that judgement 6,000
times, and every hesitation compounds into disagreement.

---

## 9. Content is not code

Day 3 produces **three scenario families, four personas, two rubrics** — written properly, as
YAML in `content/`, seeded into the database.

This is real writing work, not a fill-in-the-blank exercise. A scenario brief that says
"conduct a backend interview" produces a bland persona. One that says:

> You are a staff engineer at a mid-size fintech, forty minutes into a day of back-to-back
> screens. You are slightly behind schedule. You have read the candidate's resume once. You
> care about whether they have actually operated a system in production, and you are
> unimpressed by framework name-dropping. You have a hard stop.

...produces a counterpart that feels like a person. That difference is the entire product.

Budget a genuine half day for this. It is the cheapest quality improvement available and it
blocks the fine-tune.

---

## 10. Pitfalls that cost a day if you hit them blind

| Pitfall | Symptom | Prevention |
|---|---|---|
| Python 3.12 | `ctranslate2` won't build | 3.11 exactly |
| Forgot `selectinload` | `MissingGreenlet` | Load relationships eagerly, always |
| Hand-written TS types | Frontend renders `undefined` on day 13 | `make schema`, plus a CI drift check |
| Trusting autogenerate | Missing indexes in prod | Read every migration |
| `depends_on` without healthcheck | Flaky "connection refused" | `condition: service_healthy` |
| Baking models into the image | 4 GB image, slow cold start | Volume in dev, download on boot in prod |
| Vague rubric anchors | 0.4 inter-annotator agreement on day 19 | The three-answer test above, on day 3 |
| One OAuth app for dev + prod | Callback URL conflict | Two apps from the start |
| Same secret for JWT and WS token | Leaked ws token = leaked account | Three distinct secrets |

---

## 11. Interview questions this phase earns you

- *Why one backend language instead of a TypeScript API with Python workers?*
- *What does it mean that your realtime service is stateful, and what does that force in your
  deployment?*
- *How do your frontend and backend types stay in sync?*
- *Why is the WebSocket credential different from your session token?*
- *Why UUID v7?*
- *Why are `turn_metrics` and `turn_scores` separate tables?*

Write your answers to these into `docs/PROGRESS.md` as you go. Reconstructing them in week
five is much harder than capturing them now.

---

## 12. Checklist before Phase 1

- [ ] `make up` brings Postgres, Redis and MinIO healthy in one command
- [ ] All 15 P0 tables migrated; you can explain why `turn_metrics` ≠ `turn_scores`
- [ ] `make schema` regenerates both Pydantic and TS from one JSON Schema
- [ ] OAuth sign-in works with both GitHub and Google, end to end
- [ ] A WS token can be minted, is single-use, and expires in 2 minutes
- [ ] Three scenario families, four personas, two rubrics authored and seeded
- [ ] Every anchor descriptor passes the three-answer test
- [ ] `make test` and `make lint` pass on an empty-ish codebase

→ `phase-1-LEARN.md`
