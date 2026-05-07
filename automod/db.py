"""Database engine + session factory."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

_engine = create_async_engine(settings.database_url, future=True, echo=False)
_SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


def get_engine():  # type: ignore[no-untyped-def]
    return _engine


def reconfigure(url: str) -> None:
    """Test helper: rebind engine to a new URL (e.g. SQLite in-memory)."""
    global _engine, _SessionLocal
    _engine = create_async_engine(url, future=True, echo=False)
    _SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with _SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all() -> None:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
