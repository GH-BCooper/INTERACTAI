# Phase 6 TASK 6.4a — coach (ARQ worker). Build from the repo root.
FROM python:3.11-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
# No precompiled bytecode (~100 MB across the venv): the import-time cost is paid once per boot.
ENV UV_COMPILE_BYTECODE=0 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv
COPY pyproject.toml uv.lock ./
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/realtime/pyproject.toml services/realtime/pyproject.toml
COPY services/coach/pyproject.toml services/coach/pyproject.toml
COPY services/training/pyproject.toml services/training/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package interactai-coach \
 && find /srv/.venv \( -name __pycache__ -o -name tests -o -name test \) -type d -prune -exec rm -rf {} +

FROM python:3.11-slim-bookworm AS runtime
RUN useradd --create-home --uid 10001 app
WORKDIR /srv/services/coach
COPY --from=builder /srv/.venv /srv/.venv
ENV PATH="/srv/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY content /srv/content
COPY services/coach /srv/services/coach
USER app
# An ARQ worker has no HTTP port; its health is arq's own "can reach Redis, worker alive" check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["arq", "--check", "app.worker.WorkerSettings"]
CMD ["arq", "app.worker.WorkerSettings"]
