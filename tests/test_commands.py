"""Tests for Telegram command handlers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from automod.models import Group, GroupMember, User


def _make_update(
    chat_id: int = -100,
    chat_type: str = "supergroup",
    user_id: int = 10,
    username: str = "admin",
    first_name: str = "Admin",
    args: list[str] | None = None,
    is_admin: bool = True,
    chat_title: str = "Test Group",
) -> tuple[MagicMock, MagicMock]:
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.first_name = first_name

    chat = MagicMock()
    chat.id = chat_id
    chat.type = chat_type
    chat.title = chat_title

    # get_member returns admin or owner
    from telegram.constants import ChatMemberStatus
    member_mock = MagicMock()
    member_mock.status = ChatMemberStatus.ADMINISTRATOR if is_admin else ChatMemberStatus.MEMBER
    chat.get_member = AsyncMock(return_value=member_mock)

    msg = MagicMock()
    msg.reply_text = AsyncMock()

    update = MagicMock()
    update.effective_chat = chat
    update.effective_user = user
    update.message = msg

    context = MagicMock()
    context.args = args or []

    return update, context


@pytest.mark.asyncio
async def test_cmd_start(db_session) -> None:
    update, context = _make_update()
    from automod.commands import cmd_start
    await cmd_start(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Auto-Mod" in text


@pytest.mark.asyncio
async def test_cmd_automod_on_creates_group(db_session) -> None:
    update, context = _make_update(chat_id=-200, args=["on"])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)
    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "enabled" in reply.lower()

    # Check DB
    db_session.expire_all()
    res = await db_session.execute(select(Group).where(Group.id == -200))
    group = res.scalar_one_or_none()
    assert group is not None
    assert group.is_active is True


@pytest.mark.asyncio
async def test_cmd_automod_on_updates_existing(db_session) -> None:
    g = Group(id=-201, title="G", owner_user_id=99, is_active=False)
    db_session.add(g)
    await db_session.commit()

    update, context = _make_update(chat_id=-201, user_id=99, args=["on"])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)

    db_session.expire_all()
    res = await db_session.execute(select(Group).where(Group.id == -201))
    group = res.scalar_one()
    assert group.is_active is True


@pytest.mark.asyncio
async def test_cmd_automod_off(db_session) -> None:
    g = Group(id=-202, title="G", owner_user_id=10, is_active=True)
    db_session.add(g)
    await db_session.commit()

    update, context = _make_update(chat_id=-202, args=["off"])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)

    db_session.expire_all()
    res = await db_session.execute(select(Group).where(Group.id == -202))
    group = res.scalar_one()
    assert group.is_active is False


@pytest.mark.asyncio
async def test_cmd_automod_non_admin_blocked(db_session) -> None:
    update, context = _make_update(args=["on"], is_admin=False)
    from automod.commands import cmd_automod
    await cmd_automod(update, context)
    reply = update.message.reply_text.call_args[0][0]
    assert "admin" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_automod_only_in_group(db_session) -> None:
    update, context = _make_update(chat_type="private", args=["on"])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)
    reply = update.message.reply_text.call_args[0][0]
    assert "group" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_automod_rules_free_plan_blocked(db_session) -> None:
    g = Group(id=-203, title="G", owner_user_id=10, is_active=True, plan="free")
    db_session.add(g)
    await db_session.commit()

    update, context = _make_update(chat_id=-203, args=["rules", "no", "spam"])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "pro" in reply.lower() or "subscribe" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_automod_rules_pro_plan_works(db_session) -> None:
    g = Group(id=-204, title="G", owner_user_id=10, is_active=True, plan="pro")
    db_session.add(g)
    await db_session.commit()

    update, context = _make_update(chat_id=-204, args=["rules", "no", "crypto"])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)

    db_session.expire_all()
    res = await db_session.execute(select(Group).where(Group.id == -204))
    group = res.scalar_one()
    assert group.rules_text == "no crypto"


@pytest.mark.asyncio
async def test_cmd_automod_status(db_session, fake_redis) -> None:
    g = Group(id=-205, title="StatusGroup", owner_user_id=10, is_active=True, plan="free")
    db_session.add(g)
    await db_session.commit()

    update, context = _make_update(chat_id=-205, args=["status"])

    import automod.quota as quota_module
    from unittest.mock import patch, AsyncMock as AM

    async def fake_get_redis():
        return fake_redis

    with patch.object(quota_module, "get_redis", fake_get_redis):
        from automod.commands import cmd_automod
        await cmd_automod(update, context)

    update.message.reply_text.assert_called_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "free" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_automod_reset_warns(db_session) -> None:
    g = Group(id=-206, title="G", owner_user_id=10, is_active=True)
    u = User(id=55, username="baduser", first_name="Bad")
    db_session.add_all([g, u])
    await db_session.flush()
    m = GroupMember(group_id=-206, user_id=55, role="member", warn_count=5)
    db_session.add(m)
    await db_session.commit()

    update, context = _make_update(chat_id=-206, args=["reset_warns", "baduser"])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)

    db_session.expire_all()
    res = await db_session.execute(
        select(GroupMember).where(GroupMember.group_id == -206, GroupMember.user_id == 55)
    )
    member = res.scalar_one()
    assert member.warn_count == 0


@pytest.mark.asyncio
async def test_cmd_automod_no_args_shows_help(db_session) -> None:
    update, context = _make_update(args=[])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)
    reply = update.message.reply_text.call_args[0][0]
    assert "/automod" in reply


@pytest.mark.asyncio
async def test_cmd_stats_non_admin_blocked(db_session) -> None:
    update, context = _make_update(is_admin=False)
    from automod.commands import cmd_stats
    await cmd_stats(update, context)
    reply = update.message.reply_text.call_args[0][0]
    assert "admin" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_stats_returns_data(db_session) -> None:
    from automod.models import AuditLog
    from datetime import datetime, timezone

    g = Group(id=-207, title="G", owner_user_id=10, is_active=True)
    u = User(id=10, first_name="Admin")
    db_session.add_all([g, u])
    await db_session.flush()
    log_entry = AuditLog(
        group_id=-207,
        user_id=10,
        message_text="spam msg",
        verdict_category="spam",
        verdict_severity="high",
        verdict_confidence=0.9,
        verdict_reason="spam",
        action_taken="delete",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(log_entry)
    await db_session.commit()

    update, context = _make_update(chat_id=-207)
    from automod.commands import cmd_stats
    await cmd_stats(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "1" in reply  # 1 violation
    assert "spam" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_subscribe(db_session) -> None:
    update, context = _make_update(chat_id=-208)

    from unittest.mock import patch
    with patch("automod.stripe_handler.create_checkout_session", new_callable=AsyncMock, return_value="https://checkout.stripe.com/test"):
        from automod.commands import cmd_subscribe
        await cmd_subscribe(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "stripe.com" in reply or "checkout" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_unsubscribe_no_subscription(db_session) -> None:
    g = Group(id=-209, title="G", owner_user_id=10, is_active=True, plan="free")
    db_session.add(g)
    await db_session.commit()

    update, context = _make_update(chat_id=-209)
    from automod.commands import cmd_unsubscribe
    await cmd_unsubscribe(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "no active" in reply.lower() or "not found" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_unsubscribe_with_active_subscription(db_session) -> None:
    """Unsubscribe cancels Stripe subscription successfully."""
    g = Group(id=-210, title="G", owner_user_id=10, is_active=True, plan="pro",
              stripe_subscription_id="sub_test_active")
    db_session.add(g)
    await db_session.commit()

    update, context = _make_update(chat_id=-210)

    from unittest.mock import patch, AsyncMock, MagicMock
    import asyncio

    with patch("stripe.Subscription.cancel", return_value=MagicMock()) as mock_cancel:
        from automod.commands import cmd_unsubscribe
        await cmd_unsubscribe(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "cancelled" in reply.lower() or "cancel" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_unsubscribe_stripe_error(db_session) -> None:
    """Unsubscribe handles Stripe error gracefully."""
    g = Group(id=-211, title="G", owner_user_id=10, is_active=True, plan="pro",
              stripe_subscription_id="sub_to_fail")
    db_session.add(g)
    await db_session.commit()

    update, context = _make_update(chat_id=-211)

    from unittest.mock import patch
    with patch("stripe.Subscription.cancel", side_effect=Exception("stripe error")):
        from automod.commands import cmd_unsubscribe
        await cmd_unsubscribe(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "failed" in reply.lower() or "try again" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_automod_status_no_group(db_session, fake_redis) -> None:
    """Status command shows message if group not configured."""
    update, context = _make_update(chat_id=-212, args=["status"])

    from automod.commands import cmd_automod
    await cmd_automod(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "not configured" in reply.lower() or "automod on" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_automod_reset_warns_no_args(db_session) -> None:
    """reset_warns without username shows usage message."""
    update, context = _make_update(args=["reset_warns"])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)
    reply = update.message.reply_text.call_args[0][0]
    assert "usage" in reply.lower() or "username" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_automod_reset_warns_user_not_found(db_session) -> None:
    """reset_warns with unknown user returns appropriate message."""
    g = Group(id=-213, title="G", owner_user_id=10, is_active=True)
    db_session.add(g)
    await db_session.commit()

    update, context = _make_update(chat_id=-213, args=["reset_warns", "@ghostuser"])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "not found" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_automod_reset_warns_member_not_found(db_session) -> None:
    """reset_warns when user exists but not in group."""
    g = Group(id=-214, title="G", owner_user_id=10, is_active=True)
    u = User(id=66, username="lostuser", first_name="Lost")
    db_session.add_all([g, u])
    await db_session.commit()

    update, context = _make_update(chat_id=-214, args=["reset_warns", "lostuser"])
    from automod.commands import cmd_automod
    await cmd_automod(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "no record" in reply.lower() or "not found" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_stats_in_private_chat(db_session) -> None:
    """Stats command in private chat returns group-only message."""
    update, context = _make_update(chat_type="private")
    from automod.commands import cmd_stats
    await cmd_stats(update, context)
    reply = update.message.reply_text.call_args[0][0]
    assert "group" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_subscribe_in_private_chat(db_session) -> None:
    """Subscribe command in private chat returns group-only message."""
    update, context = _make_update(chat_type="private")
    from automod.commands import cmd_subscribe
    await cmd_subscribe(update, context)
    reply = update.message.reply_text.call_args[0][0]
    assert "group" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_subscribe_stripe_error(db_session) -> None:
    """Subscribe handles Stripe error gracefully."""
    update, context = _make_update(chat_id=-215)

    from unittest.mock import patch, AsyncMock
    with patch("automod.stripe_handler.create_checkout_session", new_callable=AsyncMock, side_effect=Exception("stripe error")):
        from automod.commands import cmd_subscribe
        await cmd_subscribe(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "failed" in reply.lower() or "try again" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_unsubscribe_in_private_chat(db_session) -> None:
    """Unsubscribe in private chat returns group-only message."""
    update, context = _make_update(chat_type="private")
    from automod.commands import cmd_unsubscribe
    await cmd_unsubscribe(update, context)
    reply = update.message.reply_text.call_args[0][0]
    assert "group" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_unsubscribe_non_admin_blocked(db_session) -> None:
    """Non-admin cannot use unsubscribe."""
    update, context = _make_update(is_admin=False)
    from automod.commands import cmd_unsubscribe
    await cmd_unsubscribe(update, context)
    reply = update.message.reply_text.call_args[0][0]
    assert "admin" in reply.lower()
