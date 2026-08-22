"""Every error the user can encounter falls into exactly one class (CLAUDE.md §6). Always
raise a subclass of AppError, never a bare Exception or a raw HTTPException — the handler
registered in app.main is what turns these into the frozen response shape:

    { "error": { "code", "message", "recovery", "fatal", "trace_id" } }
"""

from __future__ import annotations


class AppError(Exception):
    status_code: int = 500
    code: str = "ORCHESTRATION_INTERNAL_ERROR"

    def __init__(self, message: str, *, recovery: str = "", fatal: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.recovery = recovery
        self.fatal = fatal


class ValidationAppError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"

    def __init__(self, message: str = "Not found.") -> None:
        super().__init__(message, recovery="Check the id and try again.")


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"

    def __init__(self, message: str = "You do not have access to this resource.") -> None:
        super().__init__(message, recovery="Sign in with the correct account.")


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many requests.", recovery=f"Wait {retry_after_seconds}s and try again."
        )
        self.retry_after_seconds = retry_after_seconds


# ── AUTH_* ────────────────────────────────────────────────────────────────────
class AuthInvalidTokenError(AppError):
    status_code = 401
    code = "AUTH_INVALID_TOKEN"

    def __init__(self, message: str = "Invalid or expired credentials.") -> None:
        super().__init__(message, recovery="Sign in again.", fatal=True)


class AuthTokenReusedError(AppError):
    status_code = 401
    code = "AUTH_TOKEN_REUSED"

    def __init__(self) -> None:
        super().__init__(
            "This refresh token was already used.",
            recovery="Your session was revoked for safety — sign in again.",
            fatal=True,
        )


class AuthProviderError(AppError):
    status_code = 502
    code = "AUTH_PROVIDER_ERROR"

    def __init__(self, provider: str, message: str = "") -> None:
        super().__init__(
            message or f"{provider} sign-in failed.",
            recovery="Try again in a moment.",
            fatal=True,
        )


# ── ORCHESTRATION_* ─────────────────────────────────────────────────────────
class OrchestrationTokenReusedError(AppError):
    status_code = 401
    code = "ORCHESTRATION_TOKEN_REUSED"

    def __init__(self) -> None:
        super().__init__(
            "This WebSocket token was already used.",
            recovery="Request a new one from the session.",
            fatal=True,
        )


class OrchestrationProtocolMismatchError(AppError):
    status_code = 400
    code = "ORCHESTRATION_PROTOCOL_MISMATCH"

    def __init__(self, expected: str, got: str) -> None:
        super().__init__(
            f"Protocol version mismatch: expected {expected}, got {got}.",
            recovery="Reload the app to pick up the latest client.",
            fatal=True,
        )
