# Phase 6 TASK 6.4a — api. Build from the repo root: docker build -f services/api/Dockerfile .
# Layer order by change frequency: uv + lockfile first, dependencies, then source last.
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
    uv sync --frozen --no-dev --no-install-workspace --package interactai-api \
 && find /srv/.venv \( -name __pycache__ -o -name tests -o -name test \) -type d -prune -exec rm -rf {} +

FROM python:3.11-slim-bookworm AS runtime
RUN useradd --create-home --uid 10001 app
WORKDIR /srv
COPY --from=builder /srv/.venv /srv/.venv
ENV PATH="/srv/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY content ./content
COPY scripts/seed.py scripts/validate_content.py ./scripts/
COPY services/api ./services/api
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"]
CMD ["uvicorn", "app.main:app", "--app-dir", "services/api", "--host", "0.0.0.0", "--port", "8000"]
