# InteractAI

A real-time multi-agent voice simulator for practising hard conversations. You speak; an AI
persona replies out loud in character in under 1.5 seconds; a separate coach agent scores every
turn off the latency path and produces an evidence-linked report.

Full build kit and specifications: `docs/00-START-HERE (1).md`. Repository conventions
(architecture, coding standards, error taxonomy, anti-scope): `CLAUDE.md`.

## Status

Phases 0-3 complete — see `docs/PROGRESS.md`. That means: the full voice loop (VAD, endpointing,
streaming ASR, persona, streaming TTS), the turn state machine, the coach agent (scoring +
narration), and the web app — sign-in, the practice room, and the report/replay surface.

## Quick start

```bash
cp .env.example .env               # then fill in secrets and OAuth credentials — see docs/01-SETUP-GUIDE (1).md
cp apps/web/.env.example apps/web/.env.local   # only needed if you change the default local ports
uv sync --all-packages
pnpm install

make up                # postgres, redis, minio
make migrate
make seed
```

Then, in separate terminals:

```bash
make api                # http://localhost:8000/docs
make realtime           # ws://localhost:8080/ws — the voice pipeline
make coach              # ARQ worker — scoring, off the latency path
make web                # http://localhost:3000 — the app itself
```

```bash
make test               # pytest + vitest
make lint                # ruff + mypy + eslint + tsc
```

See `Makefile` for every available target.
