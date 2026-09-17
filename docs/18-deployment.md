# 18 — Deployment

Phase 6 TASK 6.4. How InteractAI runs in production, how to self-host it with zero external keys,
and the stateful rules `realtime` imposes on whoever operates it.

## Topology

| Service | Image | State | Hosting (free tier) | Scales by |
|---|---|---|---|---|
| `web` | Vercel build (or `apps/web/Dockerfile` for self-host) | none | Vercel | automatic |
| `api` | `services/api/Dockerfile` | none | HF Spaces (Docker) / any container host | replicas behind any balancer |
| `realtime` | `services/realtime/Dockerfile` | **one live session per process slot** | HF Spaces (Docker, free CPU) | more processes + **session affinity** |
| `coach` | `services/coach/Dockerfile` | none (ARQ worker) | HF Spaces (Docker, free CPU) | more workers on the same Redis |
| Postgres | managed | durable | Neon | — |
| Redis | managed | ephemeral | Upstash | — |
| Objects (recordings) | S3-compatible | durable, 30-day expiry | Supabase Storage or Cloudflare R2 | — |

Hugging Face Spaces (Docker SDK, free CPU) is used for `realtime` and `coach` because it is the only
free tier with enough resident memory for faster-whisper and Piper at the same time.

**Fallback:** run the stack locally (`docker compose -f compose.selfhost.yml up`) and expose `web`,
`api` and `realtime` through a Cloudflare Tunnel (`cloudflared tunnel --url http://localhost:3000`,
one tunnel per public hostname). WebSockets pass through Cloudflare Tunnel unchanged.

## Images

All four Dockerfiles are multi-stage, build from the repo root, and order layers by change
frequency (lockfile → dependencies → source).

- Builder: `uv sync --frozen --no-dev --no-install-workspace --package <service>`; `__pycache__`
  and vendored `tests/` directories are stripped. Runtime copies only the virtualenv.
- Non-root user (`uid 10001` / `node`). Explicit `HEALTHCHECK` in every image.
- **Model weights are never in an image layer.** `realtime` runs `deploy/fetch_models.py` on boot,
  which downloads Silero VAD and the Piper voices into the `/models` volume only if missing;
  faster-whisper caches into `HF_HOME=/models/hf`. Check: `docker history --no-trunc
  interactai-realtime | grep -iE "onnx|\.bin"` returns nothing.

Measured on 2026-09-17 (`docker image inspect -f '{{.Size}}'` = compressed content size;
`docker images` shows the unpacked size, which is what the targets refer to):

| Image | Target | `docker images` (unpacked) | Compressed |
|---|---|---|---|
| api | < 400 MB | **351 MB, met** | 86 MB |
| coach | < 400 MB | **776 MB, missed** | 180 MB |
| realtime | < 800 MB excl. weights | **1.08 GB, missed** (no weights inside) | 272 MB |

The misses are dependency weight, not image hygiene; see docs/decisions/0026.

## `realtime` is stateful — operate it accordingly

### Session affinity

A session's runtime (ring buffers, state machine, persona memory, the open WAV) lives in exactly one
process. The resume protocol (docs/03-realtime-protocol.md) reconnects to that runtime within 90 s.
**A naive round-robin balancer breaks reconnection**: the reconnect lands on a process that has
never seen the session, the resume is rejected, and the recording is finalised early. Route
`/ws?token=…` by session (the token's `session_id` claim) or run one `realtime` process per public
hostname. Hugging Face Spaces runs a single replica, which satisfies this trivially.

### Concurrency cap

`MAX_CONCURRENT_SESSIONS` (default 4) is enforced at the WebSocket handshake. At capacity the
upgrade is closed with code **4429 `RATE_LIMITED`**, and the practice room shows **"At capacity, try
again shortly"**. Nothing queues silently and nothing crashes.

### Health

| Endpoint | Meaning | Touches models? |
|---|---|---|
| `GET /health` | liveness: the process is up | **no** — answers while models are still loading |
| `GET /health/ready` | readiness: VAD, ASR and Piper voices are resident and the process is not draining | yes (reads the loaded handles) |

Model loading runs as a background task after startup, so a 60-second Whisper load never fails a
liveness probe. Route traffic on `/health/ready`. A socket that arrives before readiness is closed
with `1013 ORCHESTRATION_MODELS_LOADING` rather than crashing mid-session.

### Graceful shutdown (SIGTERM)

1. Uvicorn stops accepting connections and closes live sockets (`--timeout-graceful-shutdown 10`).
2. The lifespan hook marks the process **draining** (`/health/ready` → 503, new sockets → `1012`).
3. Every runtime still registered is finalised concurrently: in-flight utterance flushed, WAV
   closed and uploaded, session row closed, pending `score_turn` jobs retried, `generate_report`
   enqueued. Bounded by `SHUTDOWN_DRAIN_TIMEOUT_S` (default 30 s); anything still running is
   logged as `undrained`.
4. The process exits.

The orchestrator's kill grace period must exceed 10 s + `SHUTDOWN_DRAIN_TIMEOUT_S`;
`compose.selfhost.yml` sets `stop_grace_period: 45s`. Docker's default 10 s is too short.

### Memory sizing

| Component | Resident |
|---|---|
| Python + FastAPI + onnxruntime base | ~250 MB |
| faster-whisper `base.en`, int8 | ~150 MB |
| Piper voice (each; two preloaded) | ~60 MB × 2 |
| Silero VAD | ~5 MB |
| Per session: ring buffers, WAV writer, persona history | ~10–20 MB |

Rule of thumb: **~550 MB + 20 MB × MAX_CONCURRENT_SESSIONS**. The per-component rows are planning
estimates. One measured point: the self-host `realtime` container sat at **675 MiB resident**
(`docker stats`, 2026-09-17) with VAD, `base.en` and both voices loaded and no live session.

## Self-host (AS-12)

```bash
git clone https://github.com/GH-BCooper/INTERACTAI.git && cd INTERACTAI
docker compose -f compose.selfhost.yml up --build
# open http://localhost:3000 → Sign in → "Continue locally"
```

Verified 2026-09-17 from a fresh `git clone` into an empty directory with volumes removed first:
every service healthy, migrations and seed applied, "Continue locally" signed in, `/health`
answered 200 while `/health/ready` was still 503 during model load. A real replayed voice session
then ran end to end: opening line from the local model, VAD/endpointing, ASR, turn persisted,
recording uploaded to MinIO, `score_turn` and `generate_report` consumed by the coach, session
closed cleanly. **What did not work on that machine** (a CPU-only laptop, Docker Desktop):
`qwen2.5:3b-instruct` on CPU could not answer a turn inside the 12 s `thinking` watchdog, so the
persona's reply degraded to the holding line. Self-host needs either a GPU for Ollama or a smaller
persona model (set `MODEL_PERSONA` in `compose.selfhost.yml`).

Do not run the self-host stack and the dev infrastructure (`make up`) on the same host ports; set
`POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`, `MINIO_API_HOST_PORT` and `MINIO_CONSOLE_HOST_PORT` if
both must run.

No API keys. Ollama (`qwen2.5:3b-instruct`) serves persona, planner, scorer and narrator;
faster-whisper and Piper run inside `realtime`; Postgres, Redis and MinIO come from
`docker-compose.yml` (included). `SELF_HOST_LOCAL_LOGIN=true` enables a single local account
because there is no OAuth app. It is refused when `ENVIRONMENT=production`.

## Production environment checklist

Set on every service unless noted. Secrets never go in the repo.

- [ ] `ENVIRONMENT=production` (secure cookies; local login refused)
- [ ] `APP_SECRET`, `JWT_SECRET`, `WS_TOKEN_SECRET` — three distinct random values (api refuses to boot otherwise)
- [ ] `DATABASE_URL` — Neon, `postgresql+asyncpg://…?ssl=require`
- [ ] `REDIS_URL` — Upstash `rediss://…`
- [ ] `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, `S3_REGION` — Supabase Storage or R2
- [ ] `WEB_ORIGIN` (the Vercel URL), `API_BASE_URL`, `REALTIME_WS_URL` (`wss://…/ws`)
- [ ] **A second OAuth app per provider** with production callback URLs: GitHub
      `https://<api-host>/auth/github/callback`, Google `https://<api-host>/auth/google/callback`
      → `GITHUB_CLIENT_ID/SECRET`, `GOOGLE_CLIENT_ID/SECRET`. Never reuse the dev apps.
- [ ] `GROQ_API_KEY`; `MODEL_PERSONA`, `MODEL_PLANNER`, `MODEL_NARRATOR`, `MODEL_JUDGE`
- [ ] `realtime`: `MAX_CONCURRENT_SESSIONS`, `SHUTDOWN_DRAIN_TIMEOUT_S`, `HOST_CLASS` (e.g. `hf-spaces-cpu-basic`), volume at `/models`
- [ ] `web` (Vercel): `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_REALTIME_HTTP_URL`
- [ ] Run `alembic upgrade head` and `scripts/seed.py` once against the production database
- [ ] Repo secret `GROQ_API_KEY` for CI safety and nightly evaluation workflows

## Deployed instance

Not deployed from this environment: provisioning Vercel, Neon, Upstash, R2 and a Hugging Face
Space needs account credentials that live outside this repository. The images, compose file and
this checklist are the complete path; see PROGRESS.md Phase 6 for status.
