"""WS session-token validation only. Realtime never mints a token (that's the API service's
`POST /sessions/{id}/ws-token`, services/api/app/core/security.py:mint_ws_token) — it only
validates and burns one, against the exact same Redis key (`ws_token_jti:{jti}`) and the same
HS256(WS_TOKEN_SECRET) scheme, so a token minted by the API is accepted here without either
service importing the other (uv workspace members stay independent).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import jwt
from redis.asyncio import Redis

from .config import get_settings
from .exceptions import AuthInvalidTokenError, OrchestrationTokenReusedError

JWT_ALGORITHM = "HS256"


@dataclass(frozen=True)
class WsTokenClaims:
    session_id: str
    user_id: str
    jti: str


def _ws_jti_key(jti: str) -> str:
    return f"ws_token_jti:{jti}"


async def validate_and_burn_ws_token(redis: Redis, token: str) -> WsTokenClaims:
    """Step 1 of the handshake (docs/phase-1-BUILD.md TASK 1.1): signature + exp, then burn the
    jti immediately on success. A second presentation of the same token — reconnect race,
    replay, whatever the cause — must fail, so the burn happens before any other handshake step.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.ws_token_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthInvalidTokenError("WS token invalid or expired.") from exc

    claims = WsTokenClaims(
        session_id=payload["session_id"], user_id=payload["user_id"], jti=payload["jti"]
    )
    burned = await redis.getdel(_ws_jti_key(claims.jti))
    if burned is None:
        raise OrchestrationTokenReusedError()
    return claims


def token_expiry_unix(token_payload_exp: int) -> bool:
    """True if the given `exp` claim (unix seconds) is in the past. Split out only so the
    handshake tests can assert the exp check independently of Redis burn ordering."""
    return token_payload_exp < int(time.time())
