"""Task 1.1: `/health` has no dependencies; `/health/ready` reflects whether the models and
pipeline resources are actually resident — including the correct HTTP status code, not just
the JSON body (FastAPI does not special-case a returned `(body, status_code)` tuple the way
Flask does, which is exactly the bug this test guards against)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.realtime.app.main import app


def test_health_has_no_dependencies() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_reports_200_when_models_loaded() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
