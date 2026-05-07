"""DB model CRUD tests."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from automod.models import AuditLog, DEFAULT_THRESHOLDS, Group, GroupMember, StripeEvent, User


@pytest.mark.asyncio
async def test_create_group(db_session) -> None:
    g = Group(id=-100123, title="Test Group", owner_user_id=42)
    db_session.add(g)
    await db_session.commit()

    res = await db_session.execute(select(Group).where(Group.id == -100123))
    loaded = res.scalar_one()
    assert loaded.title == "Test Group"
    assert loaded.plan == "free"
    assert loaded.is_active is True
    assert loaded.action_thresholds == DEFAULT_THRESHOLDS
    assert loaded.mute_duration_minutes == 60


@pytest.mark.asyncio
async def test_create_user_and_member(db_session) -> None:
    g = Group(id=-100, title="G", owner_user_id=1)
    u = User(id=1, username="alice", first_name="Alice")
    db_session.add_all([g, u])
    await db_session.flush()
    m = GroupMember(group_id=-100, user_id=1, role="admin")
    db_session.add(m)
    await db_session.commit()

    res = await db_session.execute(select(GroupMember).where(GroupMember.group_id == -100))
    loaded = res.scalar_one()
    assert loaded.role == "admin"
    assert loaded.warn_count == 0


@pytest.mark.asyncio
async def test_audit_log_insert(db_session) -> None:
    g = Group(id=-200, title="G2", owner_user_id=2)
    u = User(id=2, first_name="Bob")
    db_session.add_all([g, u])
    await db_session.flush()
    entry = AuditLog(
        group_id=-200,
        user_id=2,
        message_text="buy crypto now",
        verdict_category="scam",
        verdict_severity="high",
        verdict_confidence=0.9,
        verdict_reason="pump-and-dump",
        action_taken="delete_and_mute",
    )
    db_session.add(entry)
    await db_session.commit()

    res = await db_session.execute(select(AuditLog))
    rows = res.scalars().all()
    assert len(rows) == 1
    assert rows[0].action_taken == "delete_and_mute"


@pytest.mark.asyncio
async def test_stripe_event_unique_id(db_session) -> None:
    e = StripeEvent(id="evt_1", type="customer.subscription.created", payload={"x": 1})
    db_session.add(e)
    await db_session.commit()
    res = await db_session.execute(select(StripeEvent).where(StripeEvent.id == "evt_1"))
    assert res.scalar_one().type == "customer.subscription.created"
