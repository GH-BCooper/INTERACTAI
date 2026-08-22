"""Three tokens, on purpose — docs/phase-0-LEARN.md §7.

Access JWT: 15 min, HS256(JWT_SECRET), claims sub/scopes/exp/iat/jti.
Refresh token: 30 days, rotating, opaque (not a JWT), stored hashed in Redis keyed by family.
WS token: 120 s, single use, HS256(WS_TOKEN_SECRET), scoped to one session.

Refresh rotation / reuse detection: each family's Redis record carries a monotonic `version`.
The token string embeds the version it was issued at. Presenting a version older than the
family's current version means a rotated-away token was replayed — theft, not a race — and
the whole family is revoked. Presenting the current version rotates it forward one step.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass

import jwt
from redis.asyncio import Redis

from ..models.base import uuid7
from .config import get_settings
from .exceptions import (
    AuthInvalidTokenError,
    AuthTokenReusedError,
    OrchestrationTokenReusedError,
)

JWT_ALGORITHM = "HS256"


# ── Access JWT ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: str
    scopes: list[str]
    jti: str


def create_access_token(user_id: str, scopes: list[str] | None = None) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": user_id,
        "scopes": scopes or [],
        "iat": now,
        "exp": now + settings.access_token_ttl_minutes * 60,
        "jti": str(uuid7()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthInvalidTokenError() from exc
    return AccessTokenClaims(
        user_id=payload["sub"], scopes=payload.get("scopes", []), jti=payload["jti"]
    )


# ── Refresh token (opaque, rotating, Redis-backed) ────────────────────────────
def _refresh_key(family_id: str) -> str:
    return f"refresh:{family_id}"


def _hash_secret(secret: str) -> str:
    # APP_SECRET as a pepper: a Redis compromise alone doesn't let an attacker verify guesses.
    peppered = f"{secret}:{get_settings().app_secret}"
    return hashlib.sha256(peppered.encode()).hexdigest()


def _encode_refresh_token(family_id: str, version: int, secret: str) -> str:
    return f"{family_id}.{version}.{secret}"


def _decode_refresh_token(token: str) -> tuple[str, int, str]:
    try:
        family_id, version_str, secret = token.split(".", 2)
        return family_id, int(version_str), secret
    except ValueError as exc:
        raise AuthInvalidTokenError("Malformed refresh token.") from exc


async def create_refresh_family(redis: Redis, user_id: str) -> str:
    settings = get_settings()
    family_id = str(uuid7())
    secret = secrets.token_urlsafe(32)
    await redis.hset(  # type: ignore[misc]  # redis-py stubs: sync/async overloads share a signature
        _refresh_key(family_id),
        mapping={"user_id": user_id, "version": 0, "secret_hash": _hash_secret(secret)},
    )
    await redis.expire(_refresh_key(family_id), settings.refresh_token_ttl_days * 86400)
    return _encode_refresh_token(family_id, 0, secret)


async def rotate_refresh_token(redis: Redis, presented_token: str) -> tuple[str, str]:
    """Returns (new_refresh_token, user_id). Raises AuthTokenReusedError (revokes the family)
    or AuthInvalidTokenError.
    """
    settings = get_settings()
    family_id, presented_version, secret = _decode_refresh_token(presented_token)
    key = _refresh_key(family_id)

    record = await redis.hgetall(key)  # type: ignore[misc]  # redis-py stubs: see hset above
    if not record:
        raise AuthInvalidTokenError("Refresh token expired or already revoked.")

    stored_version = int(record["version"])
    user_id = record["user_id"]

    if presented_version < stored_version:
        await redis.delete(key)  # theft, not a race — revoke the whole family
        raise AuthTokenReusedError()

    if presented_version > stored_version or _hash_secret(secret) != record["secret_hash"]:
        raise AuthInvalidTokenError("Refresh token does not match the current family state.")

    new_version = stored_version + 1
    new_secret = secrets.token_urlsafe(32)
    await redis.hset(  # type: ignore[misc]  # redis-py stubs: see hset above
        key, mapping={"version": new_version, "secret_hash": _hash_secret(new_secret)}
    )
    await redis.expire(key, settings.refresh_token_ttl_days * 86400)
    return _encode_refresh_token(family_id, new_version, new_secret), user_id


async def revoke_refresh_family(redis: Redis, presented_token: str) -> None:
    family_id, _version, _secret = _decode_refresh_token(presented_token)
    await redis.delete(_refresh_key(family_id))


# ── WS session token ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class WsTokenClaims:
    session_id: str
    user_id: str
    jti: str


def _ws_jti_key(jti: str) -> str:
    return f"ws_token_jti:{jti}"


async def mint_ws_token(redis: Redis, session_id: str, user_id: str) -> str:
    settings = get_settings()
    jti = str(uuid7())
    now = int(time.time())
    payload = {
        "session_id": session_id,
        "user_id": user_id,
        "jti": jti,
        "iat": now,
        "exp": now + settings.ws_token_ttl_seconds,
    }
    token = jwt.encode(payload, settings.ws_token_secret, algorithm=JWT_ALGORITHM)
    await redis.setex(_ws_jti_key(jti), settings.ws_token_ttl_seconds, "1")
    return token


async def validate_and_burn_ws_token(
    redis: Redis, token: str, *, expected_session_id: str | None = None
) -> WsTokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.ws_token_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthInvalidTokenError("WS token invalid or expired.") from exc

    claims = WsTokenClaims(
        session_id=payload["session_id"], user_id=payload["user_id"], jti=payload["jti"]
    )
    if expected_session_id is not None and claims.session_id != expected_session_id:
        raise AuthInvalidTokenError("WS token is not scoped to this session.")

    burned = await redis.getdel(_ws_jti_key(claims.jti))
    if burned is None:
        raise OrchestrationTokenReusedError()
    return claims


# ── Replay token (Task 3.4d) ───────────────────────────────────────────────────
REPLAY_TOKEN_TTL_SECONDS = 3600  # long enough to sit with one report; re-minted per page load


def mint_replay_token(session_id: str, user_id: str) -> str:
    """Scopes realtime's `POST /synthesize` (on-demand persona-audio regeneration for report
    replay, CLAUDE.md §1.8) to a session this caller has already been proven to own by the
    `CurrentUser` dependency on the route that calls this. Signed with WS_TOKEN_SECRET, same as
    a WS handshake token, but deliberately **not** single-use (`validate_and_burn_ws_token`'s
    Redis burn would break the second-and-later synthesis call of a single replay session) — see
    services/realtime/app/core/security.py:validate_replay_token for the other half."""
    settings = get_settings()
    now = int(time.time())
    payload = {
        "typ": "replay",
        "session_id": session_id,
        "user_id": user_id,
        "iat": now,
        "exp": now + REPLAY_TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, settings.ws_token_secret, algorithm=JWT_ALGORITHM)


# ── OAuth CSRF state ───────────────────────────────────────────────────────────
def _oauth_state_key(state: str) -> str:
    return f"oauth_state:{state}"


async def create_oauth_state(redis: Redis) -> str:
    settings = get_settings()
    state = secrets.token_urlsafe(24)
    await redis.setex(_oauth_state_key(state), settings.oauth_state_ttl_seconds, "1")
    return state


async def consume_oauth_state(redis: Redis, state: str) -> bool:
    return await redis.getdel(_oauth_state_key(state)) is not None
