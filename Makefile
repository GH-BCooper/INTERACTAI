# InteractAI — see CLAUDE.md §3 and docs/phase-0-BUILD.md TASK 0.1.
# Targets below are the exact names other docs reference. Do not rename them.

SHELL := /usr/bin/bash
.DEFAULT_GOAL := help
.PHONY: help up down logs migrate makemigration seed api realtime coach web schema test safety lint fmt cli eval eval-speech eval-persona eval-all images selfhost demo-record clean _sync _pnpm

help:
	@echo "InteractAI - make targets:"
	@echo "  up             docker compose up -d, wait for all-healthy"
	@echo "  down           stop containers, preserve volumes"
	@echo "  logs           follow container logs"
	@echo "  migrate        alembic upgrade head"
	@echo "  makemigration  alembic revision --autogenerate  (usage: make makemigration m=\"message\")"
	@echo "  seed           load content/ into the database (idempotent)"
	@echo "  api            run services/api with reload, port 8000"
	@echo "  realtime       run services/realtime with reload, port 8080"
	@echo "  coach          run the coach ARQ worker"
	@echo "  web            run apps/web dev server, port 3000"
	@echo "  schema         regenerate Pydantic + TS from packages/schema"
	@echo "  test           pytest + vitest (excludes the live safety suite — see 'safety')"
	@echo "  safety         the live-model safety suite (Task 2.6): real Groq/Ollama calls, slow"
	@echo "  lint           ruff + mypy + eslint + tsc --noEmit"
	@echo "  fmt            ruff format + fix"
	@echo "  cli            terminal voice harness (Phase 1 gate)"
	@echo "  eval           Level 3 scorer evaluation (writes an eval_runs row)"
	@echo "  eval-speech    Level 1 speech components: WER, RTF gates, endpointing, TTFA"
	@echo "  eval-persona   Level 2 persona adherence: breaks, repetition, plan, difficulty separation"
	@echo "  eval-all       all three levels (what the nightly workflow runs)"
	@echo "  images         build the production images for api, coach, realtime, web"
	@echo "  selfhost       the whole stack in containers, local models, zero external keys"
	@echo "  clean          remove local data volumes (asks for confirmation)"

# ── internal bootstrap prerequisites — not part of the required target list, but keep
#    `make up && make migrate && make seed` working with zero manual steps from a clean clone.
_sync:
	@uv sync --all-packages

_pnpm:
	@pnpm install --frozen-lockfile 2>/dev/null || pnpm install

up:
	docker compose up -d
	@bash scripts/wait_healthy.sh 60

down:
	docker compose down

logs:
	docker compose logs -f

migrate: _sync
	uv run --directory services/api alembic upgrade head

makemigration: _sync
	uv run --directory services/api alembic revision --autogenerate -m "$(m)"

seed: _sync
	uv run python scripts/seed.py

api: _sync
	uv run uvicorn app.main:app --reload --app-dir services/api --host 0.0.0.0 --port 8000

realtime: _sync
	uv run uvicorn app.main:app --reload --app-dir services/realtime --host 0.0.0.0 --port 8080

coach: _sync
	uv run --directory services/coach python -m arq app.worker.WorkerSettings

web: _pnpm
	pnpm --filter @interactai/web run dev

schema: _sync _pnpm
	uv run python packages/schema/generate.py
	pnpm --filter @interactai/schema run generate:ts

test: _sync _pnpm
	uv run pytest -m "not safety"
	pnpm --filter @interactai/web run test

safety: _sync
	uv run pytest tests/safety -v

lint: _sync _pnpm
	uv run ruff check .
	uv run mypy --strict services/realtime/app
	uv run mypy services/api/app
	uv run mypy services/coach/app
	pnpm --filter @interactai/web run lint
	pnpm --filter @interactai/web run typecheck

fmt: _sync
	uv run ruff format .
	uv run ruff check --fix .

cli: _sync
	uv run python scripts/cli.py

eval: _sync
	uv run python scripts/eval.py

eval-speech: _sync
	uv run python scripts/eval_speech.py

eval-persona: _sync
	uv run python scripts/eval_persona.py

eval-all: eval-speech eval-persona eval

images:
	docker build -f services/api/Dockerfile -t interactai-api .
	docker build -f services/coach/Dockerfile -t interactai-coach .
	docker build -f services/realtime/Dockerfile -t interactai-realtime .
	docker build -f apps/web/Dockerfile -t interactai-web .

selfhost:
	docker compose -f compose.selfhost.yml up --build

clean:
	@echo "This permanently deletes local Postgres, Redis and MinIO data (docker volumes)."
	@read -p "Type 'yes' to continue: " confirm; \
	if [ "$$confirm" = "yes" ]; then docker compose down -v; else echo "Aborted - nothing removed."; fi
