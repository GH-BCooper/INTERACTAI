"""ARQ worker — off the latency path (CLAUDE.md §2). `score_turn` and `generate_report`
(report/build.py) do the real work; the wrappers here add the one thing Task 2.2d needs that
build.py itself shouldn't own — "after max_tries (3), write a failed_jobs record and surface
it," which needs ARQ's own retry-count (`ctx['job_try']`), not application logic.
"""

from __future__ import annotations

import os
import uuid as std_uuid
from typing import Any

from arq.connections import RedisSettings

from .core.config import get_settings
from .core.logging import configure_logging, get_logger
from .db.repository import insert_failed_job
from .db.session import get_sessionmaker
from .report.build import generate_report as _generate_report
from .report.build import score_turn as _score_turn

logger = get_logger(__name__)


async def _record_failure(
    *,
    session_id: str,
    turn_id: str | None,
    job_name: str,
    payload: dict[str, Any],
    error: str,
    attempts: int,
) -> None:
    async with get_sessionmaker()() as db:
        await insert_failed_job(
            db,
            session_id=std_uuid.UUID(session_id),
            turn_id=std_uuid.UUID(turn_id) if turn_id else None,
            job_name=job_name,
            payload=payload,
            error=error,
            attempts=attempts,
        )
    logger.error(
        "job_permanently_failed", job_name=job_name, session_id=session_id, attempts=attempts
    )


async def score_turn(ctx: dict[str, Any], *, session_id: str, turn_id: str) -> None:
    settings = get_settings()
    try:
        await _score_turn(ctx, session_id=session_id, turn_id=turn_id)
    except Exception as exc:
        job_try = int(ctx.get("job_try", 1))
        if job_try >= settings.max_job_tries:
            await _record_failure(
                session_id=session_id,
                turn_id=turn_id,
                job_name="score_turn",
                payload={"session_id": session_id, "turn_id": turn_id},
                error=str(exc),
                attempts=job_try,
            )
            return  # recorded — no point letting ARQ retry a job we've already given up on
        raise


async def generate_report(ctx: dict[str, Any], *, session_id: str, wait_attempt: int = 0) -> None:
    settings = get_settings()
    try:
        await _generate_report(ctx, session_id=session_id, wait_attempt=wait_attempt)
    except Exception as exc:
        job_try = int(ctx.get("job_try", 1))
        if job_try >= settings.max_job_tries:
            await _record_failure(
                session_id=session_id,
                turn_id=None,
                job_name="generate_report",
                payload={"session_id": session_id},
                error=str(exc),
                attempts=job_try,
            )
            return
        raise


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()


async def shutdown(ctx: dict[str, Any]) -> None:
    pass


class WorkerSettings:
    functions = [score_turn, generate_report]
    on_startup = startup
    on_shutdown = shutdown
    max_tries = 3  # Task 2.2d: "After max_tries (3), write a failed_jobs record"
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
