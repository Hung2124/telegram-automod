"""Tests for the on_group_message moderation pipeline."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from automod.classifier import Verdict
from automod.models import AuditLog, Group, GroupMember, User


def _make_update(
    chat_id: int = -100,
    user_id: int = 42,
    text: str = "hello world",
    chat_type: str = "supergroup",
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.username = "testuser"
    user.first_name = "Test"

    chat = MagicMock()
    chat.id = chat_id
    chat.type = chat_type
    chat.title = "TestGroup"

    msg = MagicMock()
    msg.text = text
    msg.delete = AsyncMock()
    msg.reply_text = AsyncMock()

    update = MagicMock()
    update.effective_message = msg
    update.effective_chat = chat
    update.effective_user = user
    return update


def _make_context(bot: MagicMock | None = None) -> MagicMock:
    context = MagicMock()
    context.bot = bot or MagicMock()
    context.bot.restrict_chat_member = AsyncMock()
    return context


@pytest.mark.asyncio
async def test_moderation_skips_inactive_group(db_session, fake_redis) -> None:
    """Messages in inactive groups should be silently ignored."""
    group = Group(id=-100, title="G", owner_user_id=1, is_active=False)
    db_session.add(group)
    await db_session.commit()

    update = _make_update(chat_id=-100)
    context = _make_context()

    with patch("automod.moderation.classify", new_callable=AsyncMock) as mock_classify:
        with patch("automod.moderation.check_and_increment", new_callable=AsyncMock) as mock_quota:
            from automod.moderation import on_group_message
            await on_group_message(update, context)

    mock_classify.assert_not_called()
    mock_quota.assert_not_called()


@pytest.mark.asyncio
async def test_moderation_skips_unknown_group(db_session, fake_redis) -> None:
    """Messages in groups not in DB are silently ignored."""
    update = _make_update(chat_id=-999)
    context = _make_context()

    with patch("automod.moderation.classify", new_callable=AsyncMock) as mock_classify:
        from automod.moderation import on_group_message
        await on_group_message(update, context)

    mock_classify.assert_not_called()


@pytest.mark.asyncio
async def test_moderation_quota_exceeded_skips(db_session, fake_redis) -> None:
    """Silently skip when daily quota is exceeded."""
    group = Group(id=-101, title="G", owner_user_id=1, is_active=True)
    db_session.add(group)
    await db_session.commit()

    update = _make_update(chat_id=-101)
    context = _make_context()

    with patch("automod.moderation.classify", new_callable=AsyncMock) as mock_classify:
        with patch("automod.moderation.check_and_increment", new_callable=AsyncMock, return_value=False):
            from automod.moderation import on_group_message
            await on_group_message(update, context)

    mock_classify.assert_not_called()


@pytest.mark.asyncio
async def test_moderation_noop_on_ok_verdict(db_session) -> None:
    """No action taken for non-violation messages."""
    group = Group(id=-102, title="G", owner_user_id=1, is_active=True)
    db_session.add(group)
    await db_session.commit()

    update = _make_update(chat_id=-102)
    context = _make_context()

    ok_verdict = Verdict(is_violation=False, category="ok", severity="none", reason="fine", confidence=0.99)

    with patch("automod.moderation.classify", new_callable=AsyncMock, return_value=ok_verdict):
        with patch("automod.moderation.check_and_increment", new_callable=AsyncMock, return_value=True):
            from automod.moderation import on_group_message
            await on_group_message(update, context)

    update.effective_message.delete.assert_not_called()
    update.effective_message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_moderation_deletes_high_severity(db_session) -> None:
    """High severity message should be deleted and user muted."""
    group = Group(id=-103, title="G", owner_user_id=1, is_active=True)
    db_session.add(group)
    await db_session.commit()

    update = _make_update(chat_id=-103)
    context = _make_context()

    high_verdict = Verdict(is_violation=True, category="scam", severity="high", reason="scam", confidence=0.95)

    with patch("automod.moderation.classify", new_callable=AsyncMock, return_value=high_verdict):
        with patch("automod.moderation.check_and_increment", new_callable=AsyncMock, return_value=True):
            from automod.moderation import on_group_message
            await on_group_message(update, context)

    update.effective_message.delete.assert_called_once()
    context.bot.restrict_chat_member.assert_called_once()


@pytest.mark.asyncio
async def test_moderation_deletes_medium_severity(db_session) -> None:
    """Medium severity message should be deleted but not muted."""
    group = Group(id=-104, title="G", owner_user_id=1, is_active=True)
    db_session.add(group)
    await db_session.commit()

    update = _make_update(chat_id=-104)
    context = _make_context()

    med_verdict = Verdict(is_violation=True, category="spam", severity="medium", reason="spam", confidence=0.9)

    with patch("automod.moderation.classify", new_callable=AsyncMock, return_value=med_verdict):
        with patch("automod.moderation.check_and_increment", new_callable=AsyncMock, return_value=True):
            from automod.moderation import on_group_message
            await on_group_message(update, context)

    update.effective_message.delete.assert_called_once()
    context.bot.restrict_chat_member.assert_not_called()


@pytest.mark.asyncio
async def test_moderation_warns_low_severity(db_session) -> None:
    """Low severity message should get a warning reply."""
    group = Group(id=-105, title="G", owner_user_id=1, is_active=True)
    db_session.add(group)
    await db_session.commit()

    update = _make_update(chat_id=-105, user_id=50)
    context = _make_context()

    low_verdict = Verdict(is_violation=True, category="off_topic", severity="low", reason="off topic", confidence=0.8)

    with patch("automod.moderation.classify", new_callable=AsyncMock, return_value=low_verdict):
        with patch("automod.moderation.check_and_increment", new_callable=AsyncMock, return_value=True):
            from automod.moderation import on_group_message
            await on_group_message(update, context)

    update.effective_message.reply_text.assert_called_once()
    update.effective_message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_moderation_writes_audit_log(db_session) -> None:
    """Audit log entry should be written after processing."""
    group = Group(id=-106, title="G", owner_user_id=1, is_active=True)
    db_session.add(group)
    await db_session.commit()

    update = _make_update(chat_id=-106, user_id=99, text="buy cheap crypto!")
    context = _make_context()

    spam_verdict = Verdict(is_violation=True, category="spam", severity="medium", reason="spam", confidence=0.9)

    with patch("automod.moderation.classify", new_callable=AsyncMock, return_value=spam_verdict):
        with patch("automod.moderation.check_and_increment", new_callable=AsyncMock, return_value=True):
            from automod.moderation import on_group_message
            await on_group_message(update, context)

    res = await db_session.execute(select(AuditLog).where(AuditLog.group_id == -106))
    logs = res.scalars().all()
    assert len(logs) == 1
    assert logs[0].verdict_category == "spam"
    assert logs[0].action_taken == "delete"


@pytest.mark.asyncio
async def test_moderation_increments_warn_count(db_session) -> None:
    """Warn action should increment the warn_count for the group member."""
    group = Group(id=-107, title="G", owner_user_id=1, is_active=True)
    user = User(id=77, first_name="WarnUser")
    db_session.add_all([group, user])
    await db_session.flush()
    member = GroupMember(group_id=-107, user_id=77, role="member", warn_count=0)
    db_session.add(member)
    await db_session.commit()

    update = _make_update(chat_id=-107, user_id=77)
    context = _make_context()

    low_verdict = Verdict(is_violation=True, category="off_topic", severity="low", reason="off", confidence=0.8)

    with patch("automod.moderation.classify", new_callable=AsyncMock, return_value=low_verdict):
        with patch("automod.moderation.check_and_increment", new_callable=AsyncMock, return_value=True):
            from automod.moderation import on_group_message
            await on_group_message(update, context)

    db_session.expire_all()
    res = await db_session.execute(
        select(GroupMember).where(GroupMember.group_id == -107, GroupMember.user_id == 77)
    )
    updated = res.scalar_one()
    assert updated.warn_count == 1


@pytest.mark.asyncio
async def test_moderation_skips_low_confidence(db_session) -> None:
    """Messages with confidence < 0.6 should not trigger action."""
    group = Group(id=-108, title="G", owner_user_id=1, is_active=True)
    db_session.add(group)
    await db_session.commit()

    update = _make_update(chat_id=-108)
    context = _make_context()

    low_conf = Verdict(is_violation=True, category="spam", severity="high", reason="maybe", confidence=0.5)

    with patch("automod.moderation.classify", new_callable=AsyncMock, return_value=low_conf):
        with patch("automod.moderation.check_and_increment", new_callable=AsyncMock, return_value=True):
            from automod.moderation import on_group_message
            await on_group_message(update, context)

    update.effective_message.delete.assert_not_called()
