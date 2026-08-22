"""Same client construction and singleton pattern as services/api/app/core/redis_client.py —
one `redis.asyncio.Redis` per process, `decode_responses=True` so callers get str, not bytes.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from redis.asyncio import Redis

from .config import get_settings


@lru_cache
def get_redis_pool() -> Redis:
    client: Redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return client


async def get_redis() -> AsyncGenerator[Redis]:
    yield get_redis_pool()
