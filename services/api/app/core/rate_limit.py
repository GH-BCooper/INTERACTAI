"""Redis fixed-window counters (AS-10). Approximate by design — a fixed window can allow a
short burst at the boundary, which is an acceptable trade for a single INCR+EXPIRE round trip
instead of a sliding-window sorted set, at this traffic scale.
"""

from __future__ import annotations

from redis.asyncio import Redis

from .exceptions import RateLimitedError


async def enforce_rate_limit(redis: Redis, key: str, *, limit: int, window_seconds: int) -> None:
    full_key = f"ratelimit:{key}:{window_seconds}"
    count = await redis.incr(full_key)
    if count == 1:
        await redis.expire(full_key, window_seconds)
    if count > limit:
        ttl = await redis.ttl(full_key)
        raise RateLimitedError(retry_after_seconds=max(ttl, 1))
