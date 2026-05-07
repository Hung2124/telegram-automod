"""Redis-based daily quota enforcement."""
from __future__ import annotations

from datetime import date

import redis.asyncio as aioredis

from .config import settings

DAILY_LIMITS: dict[str, int | None] = {
    "free": settings.free_daily_limit,
    "pro": settings.pro_daily_limit,
    "enterprise": None,
}


def _quota_key(group_id: int) -> str:
    return f"quota:{group_id}:{date.today().isoformat()}"


async def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def check_and_increment(
    group_id: int,
    plan: str,
    *,
    redis_client: aioredis.Redis | None = None,  # type: ignore[type-arg]
) -> bool:
    """Return True if allowed, False if quota exceeded.

    Accepts an optional redis_client for testing (uses fakeredis).
    """
    limit = DAILY_LIMITS.get(plan)
    if limit is None:  # enterprise = unlimited
        return True

    key = _quota_key(group_id)

    owned = redis_client is None
    r = redis_client if redis_client is not None else await get_redis()
    try:
        current = await r.incr(key)
        if current == 1:
            await r.expire(key, 86400)
        return current <= limit
    finally:
        if owned:
            await r.aclose()
