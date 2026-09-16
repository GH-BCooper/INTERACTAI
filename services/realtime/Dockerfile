# Phase 6 TASK 6.4a — realtime. Build from the repo root.
# Model weights are NOT baked in: deploy/fetch_models.py downloads them on first boot into the
# /models volume (or they are mounted). `docker history` of this image contains no weights.
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
    uv sync --frozen --no-dev --no-install-workspace --package interactai-realtime \
 && find /srv/.venv \( -name __pycache__ -o -name tests -o -name test \) -type d -prune -exec rm -rf {} +

FROM python:3.11-slim-bookworm AS runtime
RUN useradd --create-home --uid 10001 app \
 && mkdir -p /models /srv/data/recordings && chown -R app /models /srv/data
WORKDIR /srv
COPY --from=builder /srv/.venv /srv/.venv
ENV PATH="/srv/.venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    VAD_MODEL_PATH=/models/vad/silero_vad.onnx PIPER_VOICE_DIR=/models/piper \
    HF_HOME=/models/hf
COPY deploy/fetch_models.py deploy/fetch_models.py
COPY content ./content
COPY services/realtime ./services/realtime
USER app
VOLUME ["/models"]
EXPOSE 8080
# Liveness only — never touches the models (a slow load must not read as a dead process).
# Orchestrators route traffic on GET /health/ready, which is 503 until models are resident.
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).status == 200 else 1)"]
# --timeout-graceful-shutdown bounds uvicorn's own socket close; the lifespan drain
# (SHUTDOWN_DRAIN_TIMEOUT_S) then finalises runtimes. The stop grace period must exceed both.
CMD ["sh", "-c", "python deploy/fetch_models.py && exec uvicorn app.main:app --app-dir services/realtime --host 0.0.0.0 --port 8080 --timeout-graceful-shutdown 10"]
