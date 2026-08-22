from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db
from ..core.logging import get_logger
from ..core.redis_client import get_redis
from ..core.s3 import get_s3_client

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


class HealthOut(BaseModel):
    status: str


class ReadinessOut(BaseModel):
    status: str
    postgres: bool
    redis: bool
    s3: bool


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    """Liveness — no DB, no dependencies. Just "is the process up"."""
    return HealthOut(status="ok")


@router.get("/health/ready", response_model=ReadinessOut)
async def health_ready(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> ReadinessOut:
    postgres_ok = await _check(lambda: db.execute(text("SELECT 1")), "postgres")
    redis_ok = await _check(redis.ping, "redis")
    s3_ok = await _check(lambda: asyncio.to_thread(get_s3_client().list_buckets), "s3")

    all_ok = postgres_ok and redis_ok and s3_ok
    if not all_ok:
        response.status_code = 503
    return ReadinessOut(
        status="ok" if all_ok else "degraded", postgres=postgres_ok, redis=redis_ok, s3=s3_ok
    )


async def _check(probe: Callable[[], Awaitable[object]], name: str) -> bool:
    try:
        await probe()
        return True
    except Exception as exc:  # noqa: BLE001 — a readiness probe reports false, never 500s
        logger.warning("readiness_check_failed", dependency=name, error=str(exc))
        return False
