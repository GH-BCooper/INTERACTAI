"""Phase 6 TASK 6.4d — self-host sign-in with zero external keys. Disabled by default and in
production; when enabled it issues the same access-token + refresh-cookie handoff as OAuth."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from services.api.app.core.config import get_settings


async def test_local_login_is_off_by_default(app_client: AsyncClient) -> None:
    resp = await app_client.get("/auth/local/login")
    assert resp.status_code == 404


async def test_local_login_refused_in_production(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings as api_settings

    monkeypatch.setattr(api_settings(), "self_host_local_login", True)
    monkeypatch.setattr(api_settings(), "environment", "production")
    resp = await app_client.get("/auth/local/login")
    assert resp.status_code == 404


async def test_local_login_signs_in_one_local_account(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings as api_settings

    monkeypatch.setattr(api_settings(), "self_host_local_login", True)
    first = await app_client.get("/auth/local/login")
    assert first.status_code == 307
    assert "#token=" in first.headers["location"]
    assert "interactai_refresh" in first.headers.get("set-cookie", "")

    token = first.headers["location"].split("#token=")[1].split("&")[0]
    me = await app_client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "local@selfhost.invalid"

    second = await app_client.get("/auth/local/login")
    token2 = second.headers["location"].split("#token=")[1].split("&")[0]
    me2 = await app_client.get("/me", headers={"Authorization": f"Bearer {token2}"})
    assert me2.json()["user"]["id"] == me.json()["user"]["id"]


def test_settings_default_is_disabled() -> None:
    assert get_settings().self_host_local_login is False
