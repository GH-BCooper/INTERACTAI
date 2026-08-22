"""Proves the seeded_content and authed_client fixtures (docs/phase-0-BUILD.md TASK 0.7) work,
not just that they're defined.
"""

from __future__ import annotations

from httpx import AsyncClient


async def test_seeded_content_is_queryable_through_the_api(
    app_client: AsyncClient, seeded_content: dict[str, dict[str, object]]
) -> None:
    assert len(seeded_content["persona_ids"]) == 4
    assert len(seeded_content["rubric_ids"]) == 2

    resp = await app_client.get("/scenarios")
    assert resp.status_code == 200
    assert len(resp.json()) == 9


async def test_authed_client_can_call_me(authed_client: AsyncClient) -> None:
    resp = await authed_client.get("/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["email"] == "authed-fixture-user@example.com"
