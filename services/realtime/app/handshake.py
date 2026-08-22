"""The WS handshake's pre-accept authorization decision (Task 1.1, steps 1-4), split out from
`main.py` so it is testable against fake Redis/DB/registry objects without a real socket —
this is exactly what the acceptance criteria ask for ("Token reuse, wrong owner, expired token
and closed session are each rejected with the correct code — one test per case").

Close codes are the only channel available for a pre-accept rejection: the frozen `error`
JSON message requires an already-open socket, and "reject the upgrade before accepting it" is
a hard rule (CLAUDE.md-adjacent Task 1.1 requirement: never accept-then-close). Codes are in
the 4000-4999 private-use range (RFC 6455 §7.4.2); `reason` carries our AppError `code` string
(<=123 UTF-8 bytes, comfortably enough for every code we use).
"""

from __future__ import annotations

import uuid as std_uuid
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Protocol

from redis.asyncio import Redis

from .core.config import Settings
from .core.exceptions import AuthInvalidTokenError, OrchestrationTokenReusedError
from .core.security import WsTokenClaims, validate_and_burn_ws_token
from .db.repository import get_session_row
from .session import SessionRegistry, SessionRuntime


class DbLike(Protocol):
    async def execute(self, *args: Any, **kwargs: Any) -> Any: ...


class HandshakeOutcome(Enum):
    REJECT = auto()
    FRESH = auto()
    RESUMABLE = auto()


@dataclass
class HandshakeDecision:
    outcome: HandshakeOutcome
    claims: WsTokenClaims | None = None
    session_row: dict[str, Any] | None = None
    existing_runtime: SessionRuntime | None = None
    close_code: int | None = None
    close_reason: str | None = None


CLOSE_AUTH_INVALID = 4401
CLOSE_TOKEN_REUSED = 4409
CLOSE_NOT_FOUND = 4404
CLOSE_SESSION_BUSY = 4409
CLOSE_RATE_LIMITED = 4429

_OPEN_SESSION_STATUSES = ("created", "active")


async def decide_handshake(
    *,
    token: str | None,
    redis: Redis,
    db: DbLike,
    registry: SessionRegistry,
    settings: Settings,
) -> HandshakeDecision:
    if not token:
        return HandshakeDecision(
            HandshakeOutcome.REJECT,
            close_code=CLOSE_AUTH_INVALID,
            close_reason="AUTH_INVALID_TOKEN",
        )

    try:
        claims = await validate_and_burn_ws_token(redis, token)
    except OrchestrationTokenReusedError:
        return HandshakeDecision(
            HandshakeOutcome.REJECT,
            close_code=CLOSE_TOKEN_REUSED,
            close_reason="ORCHESTRATION_TOKEN_REUSED",
        )
    except AuthInvalidTokenError:
        return HandshakeDecision(
            HandshakeOutcome.REJECT,
            close_code=CLOSE_AUTH_INVALID,
            close_reason="AUTH_INVALID_TOKEN",
        )

    session_id = std_uuid.UUID(claims.session_id)
    session_row = await get_session_row(db, session_id)  # type: ignore[arg-type]

    # Wrong owner collapses into NOT_FOUND rather than a distinct FORBIDDEN — confirming a
    # session *exists* to someone who doesn't own it is its own information leak.
    if (
        session_row is None
        or session_row["status"] not in _OPEN_SESSION_STATUSES
        or str(session_row["user_id"]) != claims.user_id
    ):
        return HandshakeDecision(
            HandshakeOutcome.REJECT, close_code=CLOSE_NOT_FOUND, close_reason="NOT_FOUND"
        )

    existing = registry.get(session_id)
    if existing is not None and not existing.finalized:
        if existing.disconnected_at is None:
            return HandshakeDecision(
                HandshakeOutcome.REJECT,
                close_code=CLOSE_SESSION_BUSY,
                close_reason="ORCHESTRATION_SESSION_BUSY",
            )
        return HandshakeDecision(
            HandshakeOutcome.RESUMABLE,
            claims=claims,
            session_row=session_row,
            existing_runtime=existing,
        )

    if len(registry) >= settings.max_concurrent_sessions:
        return HandshakeDecision(
            HandshakeOutcome.REJECT, close_code=CLOSE_RATE_LIMITED, close_reason="RATE_LIMITED"
        )

    return HandshakeDecision(HandshakeOutcome.FRESH, claims=claims, session_row=session_row)
