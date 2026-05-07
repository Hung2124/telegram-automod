"""Tests for Redis quota enforcement."""
from __future__ import annotations

import pytest

from automod.quota import check_and_increment, _quota_key


@pytest.mark.asyncio
async def test_quota_allows_within_limit(fake_redis) -> None:
    allowed = await check_and_increment(-100, "free", redis_client=fake_redis)
    assert allowed is True


@pytest.mark.asyncio
async def test_quota_blocks_when_exceeded(fake_redis) -> None:
    # Set counter just at limit
    key = _quota_key(-200)
    await fake_redis.set(key, 200)

    allowed = await check_and_increment(-200, "free", redis_client=fake_redis)
    assert allowed is False


@pytest.mark.asyncio
async def test_quota_enterprise_always_allowed(fake_redis) -> None:
    # Set counter way above any limit
    key = _quota_key(-300)
    await fake_redis.set(key, 99999)

    allowed = await check_and_increment(-300, "enterprise", redis_client=fake_redis)
    assert allowed is True


@pytest.mark.asyncio
async def test_quota_increments_counter(fake_redis) -> None:
    key = _quota_key(-400)
    await check_and_increment(-400, "pro", redis_client=fake_redis)
    await check_and_increment(-400, "pro", redis_client=fake_redis)
    count = int(await fake_redis.get(key))
    assert count == 2


@pytest.mark.asyncio
async def test_quota_ttl_set_on_first_increment(fake_redis) -> None:
    key = _quota_key(-500)
    await check_and_increment(-500, "free", redis_client=fake_redis)
    ttl = await fake_redis.ttl(key)
    assert ttl > 0


@pytest.mark.asyncio
async def test_quota_pro_limit(fake_redis) -> None:
    key = _quota_key(-600)
    await fake_redis.set(key, 5000)
    allowed = await check_and_increment(-600, "pro", redis_client=fake_redis)
    assert allowed is False


@pytest.mark.asyncio
async def test_quota_pro_within_limit(fake_redis) -> None:
    key = _quota_key(-700)
    await fake_redis.set(key, 4999)
    allowed = await check_and_increment(-700, "pro", redis_client=fake_redis)
    assert allowed is True
