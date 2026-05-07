"""Tests for database helper functions."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from automod import db as db_module
from automod.models import Base, Group


@pytest.mark.asyncio
async def test_get_engine_returns_engine() -> None:
    """get_engine() returns the current engine."""
    eng = db_module.get_engine()
    assert eng is not None


@pytest.mark.asyncio
async def test_create_all_and_drop_all() -> None:
    """create_all and drop_all work on an in-memory SQLite database."""
    original_engine = db_module._engine
    original_session = db_module._SessionLocal

    db_module.reconfigure("sqlite+aiosqlite:///:memory:")
    try:
        await db_module.create_all()
        # Verify tables exist by running a query
        async with db_module.session_scope() as session:
            # Should not raise
            from sqlalchemy import text
            result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in result.fetchall()]
            assert "groups" in tables
            assert "users" in tables
            assert "audit_log" in tables

        await db_module.drop_all()
        # Verify tables are gone
        async with db_module.session_scope() as session:
            result = await session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in result.fetchall()]
            assert "groups" not in tables
    finally:
        # Restore original engine
        db_module._engine = original_engine
        db_module._SessionLocal = original_session


@pytest.mark.asyncio
async def test_session_scope_rollback_on_error(engine) -> None:
    """session_scope rolls back on exception."""
    from sqlalchemy import select
    # Try to add a group, then raise — it should roll back
    try:
        async with db_module.session_scope() as session:
            g = Group(id=-9001, title="rollback test", owner_user_id=1)
            session.add(g)
            await session.flush()
            raise ValueError("deliberate error")
    except ValueError:
        pass

    # Group should not be in DB
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        result = await session.execute(select(Group).where(Group.id == -9001))
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_reconfigure_changes_engine() -> None:
    """reconfigure() replaces the module-level engine."""
    original_url = str(db_module._engine.url)
    db_module.reconfigure("sqlite+aiosqlite:///:memory:")
    new_url = str(db_module._engine.url)
    assert "sqlite" in new_url
    # Restore
    db_module.reconfigure(original_url)
