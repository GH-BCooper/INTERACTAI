from __future__ import annotations

from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response

from ..models.base import uuid7


async def trace_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    trace_id = str(uuid7())
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(trace_id=trace_id)
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response
