#!/usr/bin/env bash
# Blocks until every service in docker-compose.yml with a healthcheck reports "healthy",
# or exits non-zero after a timeout. Used by `make up` — see docs/phase-0-BUILD.md TASK 0.2.
set -euo pipefail

TIMEOUT_SECONDS="${1:-60}"
PROJECT_NAME="$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')"

services=$(docker compose config --services)
elapsed=0
interval=2

while true; do
  all_healthy=true
  for svc in $services; do
    # -a: without it, a one-shot container that already exited (minio-init) is invisible,
    # so it can never be found "healthy" and this loop spins until the timeout.
    cid=$(docker compose ps -a -q "$svc" 2>/dev/null || true)
    if [ -z "$cid" ]; then
      all_healthy=false
      continue
    fi
    has_health=$(docker inspect --format='{{if .State.Health}}yes{{else}}no{{end}}' "$cid" 2>/dev/null || echo "no")
    if [ "$has_health" = "no" ]; then
      # One-shot containers (minio-init) have no healthcheck — treat "exited 0" as healthy.
      state=$(docker inspect --format='{{.State.Status}}' "$cid" 2>/dev/null || echo "unknown")
      exit_code=$(docker inspect --format='{{.State.ExitCode}}' "$cid" 2>/dev/null || echo "1")
      if [ "$state" = "exited" ] && [ "$exit_code" = "0" ]; then
        continue
      elif [ "$state" = "running" ]; then
        continue
      else
        all_healthy=false
      fi
      continue
    fi
    status=$(docker inspect --format='{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "unknown")
    if [ "$status" != "healthy" ]; then
      all_healthy=false
    fi
  done

  if [ "$all_healthy" = "true" ]; then
    echo "All services healthy."
    exit 0
  fi

  if [ "$elapsed" -ge "$TIMEOUT_SECONDS" ]; then
    echo "Timed out after ${TIMEOUT_SECONDS}s waiting for services to become healthy." >&2
    docker compose ps >&2
    exit 1
  fi

  sleep "$interval"
  elapsed=$((elapsed + interval))
done
