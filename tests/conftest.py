"""Shared pytest fixtures."""
from __future__ import annotations

import os

# Set required env vars BEFORE importing app modules.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
os.environ.setdefault("STRIPE_PRO_MONTHLY_PRICE_ID", "price_pro_dummy")
os.environ.setdefault("STRIPE_ENTERPRISE_MONTHLY_PRICE_ID", "price_ent_dummy")
os.environ.setdefault("LLM_PROVIDER", "openai")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from automod import db as db_module
from automod.models import Base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    db_module._engine = eng  # type: ignore[attr-defined]
    db_module._SessionLocal = async_sessionmaker(eng, expire_on_commit=False, class_=AsyncSession)  # type: ignore[attr-defined]
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncSession:  # type: ignore[no-untyped-def]
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session


@pytest_asyncio.fixture
async def fake_redis():
    import fakeredis.aioredis as fr
    client = fr.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()
