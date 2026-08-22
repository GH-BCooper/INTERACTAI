"""Every error the realtime service can produce falls into one of CLAUDE.md §6's classes.
Always raise a subclass of AppError, never a bare Exception. The WS handshake and the ingest
path turn these into either a rejected upgrade or a frozen `error` WS message:

    { "type": "error", "code", "message", "recovery", "fatal", "trace_id" }
"""

from __future__ import annotations


class AppError(Exception):
    code: str = "ORCHESTRATION_INTERNAL_ERROR"

    def __init__(self, message: str, *, recovery: str = "", fatal: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.recovery = recovery
        self.fatal = fatal


# ── AUTH_* / token validation (mirrors services/api/app/core/exceptions.py) ─────────────────
class AuthInvalidTokenError(AppError):
    code = "AUTH_INVALID_TOKEN"

    def __init__(self, message: str = "Invalid or expired credentials.") -> None:
        super().__init__(message, recovery="Request a new session.", fatal=True)


# ── ORCHESTRATION_* ─────────────────────────────────────────────────────────────────────────
class OrchestrationTokenReusedError(AppError):
    code = "ORCHESTRATION_TOKEN_REUSED"

    def __init__(self) -> None:
        super().__init__(
            "This WebSocket token was already used.",
            recovery="Request a new one from the session.",
            fatal=True,
        )


class OrchestrationSessionBusyError(AppError):
    code = "ORCHESTRATION_SESSION_BUSY"

    def __init__(self) -> None:
        super().__init__(
            "This session already has a live connection.",
            recovery="Close the other tab or device and try again.",
            fatal=True,
        )


class OrchestrationHandshakeTimeoutError(AppError):
    code = "ORCHESTRATION_HANDSHAKE_TIMEOUT"

    def __init__(self) -> None:
        super().__init__(
            "No hello message arrived in time.",
            recovery="Reconnect and try again.",
            fatal=True,
        )


class OrchestrationSessionLostError(AppError):
    code = "ORCHESTRATION_SESSION_LOST"

    def __init__(self) -> None:
        super().__init__(
            "The session runtime no longer exists on this server.",
            recovery="Start a new session — this one cannot be resumed.",
            fatal=True,
        )


class OrchestrationProtocolMismatchError(AppError):
    code = "ORCHESTRATION_PROTOCOL_MISMATCH"

    def __init__(self, expected: str, got: str) -> None:
        super().__init__(
            f"Protocol version mismatch: expected {expected}, got {got}.",
            recovery="Reload the app to pick up the latest client.",
            fatal=True,
        )


class NotFoundError(AppError):
    code = "NOT_FOUND"

    def __init__(self, message: str = "Not found.") -> None:
        super().__init__(message, recovery="Check the session id and try again.", fatal=True)


class RateLimitedError(AppError):
    code = "RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many concurrent sessions.",
            recovery=f"Wait {retry_after_seconds}s and try again.",
            fatal=True,
        )
        self.retry_after_seconds = retry_after_seconds


# ── CAPTURE_* ────────────────────────────────────────────────────────────────────────────────
class CaptureFrameMalformedError(AppError):
    code = "CAPTURE_FRAME_MALFORMED"

    def __init__(self, message: str) -> None:
        super().__init__(message, recovery="Frame dropped; capture continues.", fatal=False)
