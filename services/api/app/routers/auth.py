from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.db import get_db
from ..core.exceptions import AppError, AuthInvalidTokenError, AuthProviderError, NotFoundError
from ..core.rate_limit import enforce_rate_limit
from ..core.redis_client import get_redis
from ..core.security import (
    consume_oauth_state,
    create_access_token,
    create_oauth_state,
    create_refresh_family,
    revoke_refresh_family,
    rotate_refresh_token,
)
from ..schemas.auth import TokenResponse
from ..services import auth_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "interactai_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        token,
        httponly=True,
        # http://localhost has no TLS; a Secure cookie would never be sent back there.
        secure=settings.environment not in ("development", "selfhost"),
        samesite="lax",
        path="/auth",
        max_age=settings.refresh_token_ttl_days * 86400,
    )


async def _enforce_auth_rate_limit(
    request: Request, redis: Annotated[Redis, Depends(get_redis)]
) -> None:
    settings = get_settings()
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(
        redis,
        f"auth_ip:{client_ip}",
        limit=settings.auth_rate_limit_per_minute,
        window_seconds=60,
    )


LOCAL_USER_EMAIL = "local@selfhost.invalid"


@router.get("/local/login", dependencies=[Depends(_enforce_auth_rate_limit)])
async def local_login(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    """Phase 6 TASK 6.4d — the self-host sign-in. Enabled only by SELF_HOST_LOCAL_LOGIN and never
    in production: it signs the browser into a single local account with no credential at all,
    which is exactly right for `docker compose up` on your own machine and exactly wrong anywhere
    else. Same token/cookie handoff as the OAuth callback below."""
    settings = get_settings()
    if not settings.self_host_local_login or settings.environment == "production":
        raise NotFoundError("Local sign-in is disabled on this deployment.")

    user = await user_service.get_or_create_local_user(db, email=LOCAL_USER_EMAIL)
    await db.commit()
    access_token = create_access_token(str(user.id))
    refresh_token = await create_refresh_family(redis, str(user.id))
    expires_in = settings.access_token_ttl_minutes * 60
    location = f"{settings.web_origin}/auth/callback#token={access_token}&expires_in={expires_in}"
    response = Response(status_code=307, headers={"Location": location})
    _set_refresh_cookie(response, refresh_token)
    return response


@router.get("/{provider}/login", dependencies=[Depends(_enforce_auth_rate_limit)])
async def login(
    provider: Literal["github", "google"],
    redis: Annotated[Redis, Depends(get_redis)],
) -> Response:
    settings = get_settings()
    state = await create_oauth_state(redis)
    redirect_uri = f"{settings.api_base_url}/auth/{provider}/callback"
    authorize_url = auth_service.build_authorize_url(
        provider, state=state, redirect_uri=redirect_uri
    )
    return Response(status_code=307, headers={"Location": authorize_url})


@router.get("/{provider}/callback", dependencies=[Depends(_enforce_auth_rate_limit)])
async def callback(
    provider: Literal["github", "google"],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> Response:
    """The OAuth provider redirects the browser here directly (this is a top-level navigation,
    not a fetch a frontend origin could intercept) — so this handler's job isn't to hand the
    access token back to *a caller*, it's to get the browser to `WEB_ORIGIN` with one. Task
    3.1's app shell needs a real sign-in flow, and returning JSON here (the original Phase 0
    shape) would just strand the user on a bare API response with no way for the SPA to ever see
    the token (docs/decisions/0013).

    The refresh token still goes in the httpOnly cookie exactly as before — that's a `Set-Cookie`
    header on this same redirect response, unaffected by the body changing from JSON to a
    Location header. The access token travels in the URL **fragment** (`#...`), not a query
    string: fragments are never sent to the server on the next request and never appear in
    server access logs, which matters for a value that's otherwise bearer-equivalent for 15
    minutes."""
    settings = get_settings()

    if not await consume_oauth_state(redis, state):
        raise AuthProviderError(provider, "OAuth state was missing, expired or already used.")

    redirect_uri = f"{settings.api_base_url}/auth/{provider}/callback"
    user_info = await auth_service.exchange_code_for_user(
        provider, code=code, redirect_uri=redirect_uri
    )

    user = await user_service.find_or_link_or_create_oauth_user(
        db,
        provider=provider,
        provider_id=user_info.provider_id,
        email=user_info.email,
        email_verified=user_info.email_verified,
        name=user_info.name,
        avatar_url=user_info.avatar_url,
    )
    await db.commit()

    access_token = create_access_token(str(user.id))
    refresh_token = await create_refresh_family(redis, str(user.id))

    expires_in = settings.access_token_ttl_minutes * 60
    location = f"{settings.web_origin}/auth/callback#token={access_token}&expires_in={expires_in}"
    response = Response(status_code=307, headers={"Location": location})
    _set_refresh_cookie(response, refresh_token)
    return response


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    redis: Annotated[Redis, Depends(get_redis)],
) -> TokenResponse:
    settings = get_settings()
    presented = request.cookies.get(REFRESH_COOKIE_NAME)
    if not presented:
        raise AuthInvalidTokenError("No refresh cookie present.")

    try:
        new_token, user_id = await rotate_refresh_token(redis, presented)
    except AppError:
        response.delete_cookie(REFRESH_COOKIE_NAME, path="/auth")
        raise

    _set_refresh_cookie(response, new_token)
    access_token = create_access_token(user_id)
    return TokenResponse(
        access_token=access_token, expires_in=settings.access_token_ttl_minutes * 60
    )


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    presented = request.cookies.get(REFRESH_COOKIE_NAME)
    if presented:
        await revoke_refresh_family(redis, presented)
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/auth")
