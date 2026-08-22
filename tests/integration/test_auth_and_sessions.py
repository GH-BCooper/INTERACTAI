"""Task 0.5 acceptance criteria that can be verified by execution — docs/phase-0-BUILD.md.

Not automatable here (needs a human + a real browser): the full GitHub/Google OAuth round
trip. Everything downstream of "we have a verified OAuthUserInfo" — user linking, token
issuance, refresh rotation, WS token lifecycle, cascade deletion — is covered.
"""

from __future__ import annotations

import time

import jwt
import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.core.config import get_settings
from services.api.app.core.exceptions import (
    AuthInvalidTokenError,
    AuthTokenReusedError,
    OrchestrationTokenReusedError,
)
from services.api.app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    create_refresh_family,
    mint_ws_token,
    rotate_refresh_token,
    validate_and_burn_ws_token,
)
from services.api.app.models import Profile, User
from services.api.app.models import Session as SessionModel


async def _make_user(db_session: AsyncSession, email: str) -> User:
    user = User(email=email)
    db_session.add(user)
    await db_session.flush()
    return user


class TestRefreshRotation:
    async def test_rotation_issues_a_new_token_and_the_old_one_stops_working(
        self, redis_client: Redis
    ) -> None:
        token_v0 = await create_refresh_family(redis_client, "user-123")
        token_v1, user_id = await rotate_refresh_token(redis_client, token_v0)
        assert user_id == "user-123"
        assert token_v1 != token_v0

        # v1 works again (this is normal rotation, not reuse).
        token_v2, _ = await rotate_refresh_token(redis_client, token_v1)
        assert token_v2 != token_v1

    async def test_presenting_a_rotated_away_token_revokes_the_whole_family(
        self, redis_client: Redis
    ) -> None:
        token_v0 = await create_refresh_family(redis_client, "user-456")
        token_v1, _ = await rotate_refresh_token(redis_client, token_v0)

        # token_v0 was already rotated away — presenting it again is theft, not a race.
        with pytest.raises(AuthTokenReusedError):
            await rotate_refresh_token(redis_client, token_v0)

        # The family is now dead — even the *valid* successor token no longer works.
        with pytest.raises(AuthInvalidTokenError):
            await rotate_refresh_token(redis_client, token_v1)


class TestWsToken:
    async def test_valid_once_then_rejected(self, redis_client: Redis) -> None:
        token = await mint_ws_token(redis_client, "session-abc", "user-abc")
        claims = await validate_and_burn_ws_token(redis_client, token)
        assert claims.session_id == "session-abc"
        assert claims.user_id == "user-abc"

        with pytest.raises(OrchestrationTokenReusedError):
            await validate_and_burn_ws_token(redis_client, token)

    async def test_rejected_after_expiry(self, redis_client: Redis) -> None:
        settings = get_settings()
        now = int(time.time())
        expired_payload = {
            "session_id": "session-xyz",
            "user_id": "user-xyz",
            "jti": "some-jti",
            "iat": now - 200,
            "exp": now - 80,  # expired 80s ago
        }
        expired_token = jwt.encode(
            expired_payload, settings.ws_token_secret, algorithm=JWT_ALGORITHM
        )
        with pytest.raises(AuthInvalidTokenError):
            await validate_and_burn_ws_token(redis_client, expired_token)

    async def test_rejected_for_a_different_session(self, redis_client: Redis) -> None:
        token = await mint_ws_token(redis_client, "session-1", "user-1")
        with pytest.raises(AuthInvalidTokenError):
            await validate_and_burn_ws_token(redis_client, token, expected_session_id="session-2")


class TestSettingsSecretsGuard:
    def test_refuses_when_jwt_and_ws_secret_match(self) -> None:
        from services.api.app.core.config import Settings

        with pytest.raises(ValueError, match="WS_TOKEN_SECRET"):
            Settings(
                app_secret="a" * 32,  # noqa: S106 — dummy value for a config-validation test
                jwt_secret="shared-secret",  # noqa: S106
                ws_token_secret="shared-secret",  # noqa: S106
                database_url="postgresql+asyncpg://x:x@localhost/x",
                redis_url="redis://localhost/0",
                s3_endpoint="http://localhost:9000",
                s3_access_key="x",
                s3_secret_key="x",  # noqa: S106
                s3_bucket="x",
            )


class TestWsTokenMintingEndpoint:
    async def test_owner_can_mint_a_ws_token_and_non_owner_cannot(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        owner = await _make_user(db_session, "owner@example.com")
        other = await _make_user(db_session, "other@example.com")

        from services.api.app.models import Persona, Scenario

        persona = Persona(
            slug="p1",
            name="P",
            archetype="interviewer",
            temperament="warm",
            voice_id="en_US-lessac-medium",
            brief="A persona.",
        )
        db_session.add(persona)
        await db_session.flush()
        scenario = Scenario(
            slug="s1",
            family="technical",
            difficulty="standard",
            title="T",
            brief="x" * 210,
            opening_strategy="Open.",
            difficulty_params={"standard": {}},
            persona_id=persona.id,
        )
        db_session.add(scenario)
        await db_session.flush()
        session = SessionModel(
            user_id=owner.id,
            scenario_id=scenario.id,
            target_minutes=10,
            brief={},
        )
        db_session.add(session)
        await db_session.flush()
        await db_session.commit()

        owner_token = create_access_token(str(owner.id))
        other_token = create_access_token(str(other.id))

        resp = await app_client.post(
            f"/sessions/{session.id}/ws-token",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "token" in body and body["expires_in"] > 0

        resp_forbidden = await app_client.post(
            f"/sessions/{session.id}/ws-token",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert resp_forbidden.status_code == 403
        assert resp_forbidden.json()["error"]["code"] == "FORBIDDEN"


class TestDeleteMe:
    async def test_deletes_every_row_and_the_s3_prefix(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        user = await _make_user(db_session, "delete-me@example.com")
        db_session.add(Profile(user_id=user.id, resume_text="hello"))
        await db_session.commit()

        access_token = create_access_token(str(user.id))
        resp = await app_client.delete("/me", headers={"Authorization": f"Bearer {access_token}"})
        assert resp.status_code == 204

        remaining_users = await db_session.scalar(
            select(func.count()).select_from(User).where(User.id == user.id)
        )
        remaining_profiles = await db_session.scalar(
            select(func.count()).select_from(Profile).where(Profile.user_id == user.id)
        )
        assert remaining_users == 0
        assert remaining_profiles == 0

    async def test_delete_me_purges_the_users_s3_prefix(
        self, app_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        from services.api.app.core.s3 import delete_prefix, get_s3_client

        settings = get_settings()
        user = await _make_user(db_session, "s3-delete-me@example.com")
        await db_session.commit()

        key = f"users/{user.id}/recordings/turn-1.opus"
        get_s3_client().put_object(Bucket=settings.s3_bucket, Key=key, Body=b"fake-audio")

        access_token = create_access_token(str(user.id))
        resp = await app_client.delete("/me", headers={"Authorization": f"Bearer {access_token}"})
        assert resp.status_code == 204

        listing = get_s3_client().list_objects_v2(
            Bucket=settings.s3_bucket, Prefix=f"users/{user.id}/"
        )
        assert listing.get("KeyCount", 0) == 0
        # sanity: delete_prefix is idempotent on an already-empty prefix
        assert await delete_prefix(f"users/{user.id}/") == 0


class TestRateLimit:
    async def test_returns_429_with_retry_after_once_the_window_is_exhausted(
        self, app_client: AsyncClient
    ) -> None:
        settings = get_settings()
        last_status = None
        for _ in range(settings.auth_rate_limit_per_minute + 1):
            resp = await app_client.get("/auth/github/login", follow_redirects=False)
            last_status = resp.status_code
        assert last_status == 429
        assert resp.headers.get("Retry-After") is not None
        assert resp.json()["error"]["code"] == "RATE_LIMITED"
