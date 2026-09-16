"""Task 1.1 / Phase 6 TASK 6.4b: `/health` (liveness) has no dependencies and answers while models
are still loading; `/health/ready` reflects whether models and pipeline resources are actually
resident — including the correct HTTP status code, not just the JSON body — and goes 503 again
while the process drains on shutdown."""

from __future__ import annotations

import asyncio
import threading
import time
import uuid as std_uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services.realtime.app import main as realtime_main
from services.realtime.app.main import app
from services.realtime.app.session import SessionRegistry, drain_sessions


def _wait_ready(client: TestClient, timeout_s: float = 120.0) -> Any:
    deadline = time.monotonic() + timeout_s
    response = client.get("/health/ready")
    while response.status_code != 200 and time.monotonic() < deadline:
        time.sleep(0.25)
        response = client.get("/health/ready")
    return response


def test_health_has_no_dependencies() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_reports_200_when_models_loaded() -> None:
    with TestClient(app) as client:
        response = _wait_ready(client)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_passes_while_models_load_and_readiness_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = threading.Event()
    real_loader = realtime_main._load_models

    async def slow_loader(models: realtime_main.ModelRegistry) -> None:
        await asyncio.to_thread(release.wait, 30)
        await real_loader(models)

    monkeypatch.setattr(realtime_main, "_load_models", slow_loader)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        not_ready = client.get("/health/ready")
        assert not_ready.status_code == 503
        assert not_ready.json() == {"status": "not_ready"}
        release.set()
        assert _wait_ready(client).status_code == 200


class _FakeRuntime:
    def __init__(self) -> None:
        self.session_id = std_uuid.uuid4()
        self.finalized = False
        self.disconnected_at: float | None = None


async def test_drain_finalizes_every_active_session() -> None:
    registry = SessionRegistry()
    runtimes = [_FakeRuntime() for _ in range(5)]
    for rt in runtimes:
        registry.try_register(rt)  # type: ignore[arg-type]
    flushed: list[std_uuid.UUID] = []

    async def finalizer(rt: Any) -> None:
        await asyncio.sleep(0.01)  # stands in for the recording upload
        flushed.append(rt.session_id)

    undrained = await drain_sessions(registry, finalizer, timeout_s=5)
    assert undrained == []
    assert sorted(flushed) == sorted(rt.session_id for rt in runtimes)
    assert len(registry) == 0


async def test_drain_is_bounded_by_timeout() -> None:
    registry = SessionRegistry()
    stuck = _FakeRuntime()
    registry.try_register(stuck)  # type: ignore[arg-type]

    async def hung_finalizer(_rt: Any) -> None:
        await asyncio.sleep(60)

    undrained = await drain_sessions(registry, hung_finalizer, timeout_s=0.05)
    assert undrained == [stuck.session_id]
