"""FastAPI at port 8000. Stateless. Never touches audio (CLAUDE.md §2)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import get_settings
from .core.db import get_engine
from .core.exceptions import AppError
from .core.logging import configure_logging, get_logger
from .core.middleware import trace_id_middleware
from .core.redis_client import get_redis_pool
from .routers import (
    annotate,
    auth,
    health,
    me,
    observability,
    personas,
    registry,
    rubrics,
    scenarios,
    sessions,
)
from .schemas.common import ErrorBody, ErrorResponse

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    configure_logging()
    get_settings()  # raises at boot if JWT_SECRET == WS_TOKEN_SECRET / APP_SECRET — never lazily
    logger.info("api_startup", environment=get_settings().environment)
    yield
    await get_engine().dispose()
    await get_redis_pool().aclose()


app = FastAPI(title="InteractAI API", version="0.1.0", lifespan=lifespan)

app.middleware("http")(trace_id_middleware)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _trace_id(request: Request) -> str:
    trace_id = getattr(request.state, "trace_id", "unknown")
    return str(trace_id)


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    recovery: str = "",
    fatal: bool = False,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, recovery=recovery, fatal=fatal, trace_id=_trace_id(request)
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(), headers=headers)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    retry_after = getattr(exc, "retry_after_seconds", None)
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        recovery=exc.recovery,
        fatal=exc.fatal,
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message=str(exc.errors()),
        recovery="Check the request body against the API schema.",
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "NOT_FOUND" if exc.status_code == 404 else "ORCHESTRATION_INTERNAL_ERROR"
    return _error_response(request, status_code=exc.status_code, code=code, message=str(exc.detail))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", error=str(exc))
    return _error_response(
        request,
        status_code=500,
        code="ORCHESTRATION_INTERNAL_ERROR",
        message="Something went wrong on our end.",
        recovery="Try again in a moment.",
        fatal=True,
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(scenarios.router)
app.include_router(personas.router)
app.include_router(rubrics.router)
app.include_router(sessions.router)
app.include_router(annotate.router)
app.include_router(registry.router)
app.include_router(observability.router)
