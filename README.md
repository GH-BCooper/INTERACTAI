# InteractAI

A real-time multi-agent voice simulator for practising hard conversations. You speak; an AI
persona replies out loud in character in under 1.5 seconds; a separate coach agent scores every
turn off the latency path and produces an evidence-linked report.

Full build kit and specifications: `docs/00-START-HERE (1).md`. Repository conventions
(architecture, coding standards, error taxonomy, anti-scope): `CLAUDE.md`.

## Status

Phase 0 (Foundation) complete — see `docs/PROGRESS.md`.

## Quick start

```bash
cp .env.example .env   # then fill in secrets and OAuth credentials — see docs/01-SETUP-GUIDE (1).md
uv sync --all-packages
pnpm install

make up                # postgres, redis, minio
make migrate
make seed

make api                # http://localhost:8000/docs
```

```bash
make test               # pytest + vitest
make lint                # ruff + mypy + eslint + tsc
```

See `Makefile` for every available target.
