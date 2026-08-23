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


@dataclass(frozen=True)
class ReplayTokenClaims:
    session_id: str
    user_id: str


def validate_replay_token(token: str, *, expected_session_id: str) -> ReplayTokenClaims:
    """Task 3.4d's on-demand persona-audio-regeneration endpoint (`POST /synthesize`) needs
    *some* proof the caller owns the session being replayed, without realtime learning to
    verify the API's access/refresh tokens (CLAUDE.md §1.3 / this module's own docstring: "it
    never mints or verifies an access/refresh token itself"). The API mints this exactly like a
    WS token — same secret, same HS256 scheme — except **not single-use**: a report replay
    makes many of these calls while a user scrubs back and forth, and burning the jti on first
    use would break every call after the first. `typ: "replay"` keeps it from ever being
    confused with (or substitutable for) an actual WS handshake token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.ws_token_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthInvalidTokenError("Replay token invalid or expired.") from exc

    if payload.get("typ") != "replay":
        raise AuthInvalidTokenError("Wrong token type for this endpoint.")
    session_id = payload.get("session_id")
    if session_id is None or session_id != expected_session_id:
        raise AuthInvalidTokenError("Replay token is not scoped to this session.")
    return ReplayTokenClaims(session_id=session_id, user_id=payload["user_id"])


@dataclass(frozen=True)
class VoicePreviewTokenClaims:
    voice_id: str
    user_id: str


def validate_voice_preview_token(token: str, *, expected_voice_id: str) -> VoicePreviewTokenClaims:
    """Task 4.2's scenario-library voice preview — same secret/scheme as a WS or replay token,
    `typ: "voice_preview"` so it can never substitute for either. Minted by the API service's
    `POST /personas/{id}/voice-preview-token` (services/api/app/core/security.py::
    mint_voice_preview_token); not single-use, since a settings/library page may reasonably let
    someone replay the same preview a few times."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.ws_token_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthInvalidTokenError("Voice preview token invalid or expired.") from exc

    if payload.get("typ") != "voice_preview":
        raise AuthInvalidTokenError("Wrong token type for this endpoint.")
    voice_id = payload.get("voice_id")
    if voice_id is None or voice_id != expected_voice_id:
        raise AuthInvalidTokenError("Voice preview token is not scoped to this voice.")
    return VoicePreviewTokenClaims(voice_id=voice_id, user_id=payload["user_id"])
