"""Telegram command handlers."""
from __future__ import annotations

import structlog
from sqlalchemy import select, update

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatMemberStatus

from .db import session_scope
from .models import Group, User, GroupMember

log = structlog.get_logger()

ADMIN_STATUSES = {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}


async def _is_group_admin(update: Update) -> bool:
    """Return True if the update's user is a group admin/owner."""
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return False
    try:
        member = await chat.get_member(user.id)
        return member.status in ADMIN_STATUSES
    except Exception:
        return False


async def _upsert_user(session, user) -> None:  # type: ignore[no-untyped-def]
    existing = await session.get(User, user.id)
    if existing is None:
        session.add(User(
            id=user.id,
            username=user.username,
            first_name=user.first_name or "",
        ))
    else:
        existing.username = user.username
        existing.first_name = user.first_name or ""


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text(
        "👋 Welcome! I am **Auto-Mod** — an AI-powered moderation bot.\n\n"
        "Add me to your group, grant **Delete messages + Restrict users** permissions,\n"
        "then run /automod on to enable moderation.\n\n"
        "📦 Free plan: 1 group, 200 msg/day. Pro $9/group/month — /subscribe",
        parse_mode="Markdown",
    )


async def cmd_automod(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user:
        return

    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("This command only works in groups.")
        return

    args = context.args or []
    sub = args[0].lower() if args else ""

    if sub == "on":
        if not await _is_group_admin(update):
            await msg.reply_text("Only group admins can use this command.")
            return
        async with session_scope() as session:
            await _upsert_user(session, user)
            existing = await session.get(Group, chat.id)
            if existing is None:
                session.add(Group(
                    id=chat.id,
                    title=chat.title or "",
                    owner_user_id=user.id,
                    is_active=True,
                ))
            else:
                existing.is_active = True
                existing.title = chat.title or existing.title
        await msg.reply_text("✅ Auto-Mod enabled for this group.")

    elif sub == "off":
        if not await _is_group_admin(update):
            await msg.reply_text("Only group admins can use this command.")
            return
        async with session_scope() as session:
            existing = await session.get(Group, chat.id)
            if existing:
                existing.is_active = False
        await msg.reply_text("⏸ Auto-Mod disabled for this group.")

    elif sub == "rules":
        if not await _is_group_admin(update):
            await msg.reply_text("Only group admins can use this command.")
            return
        rules_text = " ".join(args[1:]).strip()
        async with session_scope() as session:
            group = await session.get(Group, chat.id)
            if group is None:
                await msg.reply_text("Run /automod on first.")
                return
            if group.plan == "free":
                await msg.reply_text("Custom rules require a Pro plan. Run /subscribe to upgrade.")
                return
            group.rules_text = rules_text
        await msg.reply_text(f"✅ Rules updated:\n{rules_text or '(cleared)'}")

    elif sub == "status":
        if not await _is_group_admin(update):
            await msg.reply_text("Only group admins can use this command.")
            return
        async with session_scope() as session:
            group = await session.get(Group, chat.id)
            if group is None:
                await msg.reply_text("Auto-Mod is not configured for this group. Run /automod on.")
                return
            from datetime import date
            from .quota import _quota_key
            try:
                from .quota import get_redis
                r = await get_redis()
                key = _quota_key(chat.id)
                used_raw = await r.get(key)
                await r.aclose()
                used = int(used_raw) if used_raw else 0
            except Exception:
                used = 0
            from .config import settings
            limits = {"free": settings.free_daily_limit, "pro": settings.pro_daily_limit, "enterprise": "∞"}
            limit = limits.get(group.plan, "∞")
            status_icon = "✅" if group.is_active else "⏸"
            await msg.reply_text(
                f"{status_icon} **Auto-Mod Status** for {chat.title}\n\n"
                f"Plan: {group.plan}\n"
                f"Active: {group.is_active}\n"
                f"Quota today: {used}/{limit}\n"
                f"Mute duration: {group.mute_duration_minutes} min\n"
                f"Rules: {group.rules_text or '(default)'}",
                parse_mode="Markdown",
            )

    elif sub == "reset_warns":
        if not await _is_group_admin(update):
            await msg.reply_text("Only group admins can use this command.")
            return
        if len(args) < 2:
            await msg.reply_text("Usage: /automod reset_warns @username")
            return
        target_username = args[1].lstrip("@")
        async with session_scope() as session:
            # find user by username
            res = await session.execute(select(User).where(User.username == target_username))
            target_user = res.scalar_one_or_none()
            if target_user is None:
                await msg.reply_text(f"User @{target_username} not found in database.")
                return
            res2 = await session.execute(
                select(GroupMember).where(
                    GroupMember.group_id == chat.id,
                    GroupMember.user_id == target_user.id,
                )
            )
            member = res2.scalar_one_or_none()
            if member is None:
                await msg.reply_text(f"@{target_username} has no record in this group.")
                return
            member.warn_count = 0
        await msg.reply_text(f"✅ Warn count reset for @{target_username}.")

    else:
        await msg.reply_text(
            "⚙️ **Auto-Mod Commands**\n\n"
            "/automod on — enable moderation\n"
            "/automod off — disable moderation\n"
            "/automod status — show current config + quota\n"
            "/automod rules <text> — set custom rules (Pro+)\n"
            "/automod reset_warns @user — reset warn count",
            parse_mode="Markdown",
        )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    chat = update.effective_chat
    if not msg or not chat:
        return

    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("This command only works in groups.")
        return

    if not await _is_group_admin(update):
        await msg.reply_text("Only group admins can use this command.")
        return

    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func
    from .models import AuditLog

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    async with session_scope() as session:
        res = await session.execute(
            select(AuditLog).where(
                AuditLog.group_id == chat.id,
                AuditLog.created_at >= cutoff,
            )
        )
        logs = res.scalars().all()

    total = len(logs)
    violations = [l for l in logs if l.verdict_category != "ok"]
    by_category: dict[str, int] = {}
    for l in violations:
        by_category[l.verdict_category] = by_category.get(l.verdict_category, 0) + 1

    breakdown = "\n".join(f"  {cat}: {cnt}" for cat, cnt in sorted(by_category.items()))
    await msg.reply_text(
        f"📊 **Stats for {chat.title}** (last 24h)\n\n"
        f"Messages scanned: {total}\n"
        f"Violations: {len(violations)}\n"
        f"\nBreakdown by category:\n{breakdown or '  (none)'}",
        parse_mode="Markdown",
    )


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user:
        return

    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("This command only works in groups.")
        return

    if not await _is_group_admin(update):
        await msg.reply_text("Only group admins can use this command.")
        return

    try:
        from .stripe_handler import create_checkout_session
        from .config import settings
        url = await create_checkout_session(
            group_id=chat.id,
            user_id=user.id,
            price_id=settings.stripe_pro_monthly_price_id,
        )
        await msg.reply_text(
            f"💳 **Subscribe to Pro Plan**\n\n"
            f"Click the link below to complete payment:\n{url}",
            parse_mode="Markdown",
        )
    except Exception as e:
        log.error("subscribe_failed", err=str(e))
        await msg.reply_text("Failed to create checkout session. Please try again later.")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user:
        return

    if chat.type not in ("group", "supergroup"):
        await msg.reply_text("This command only works in groups.")
        return

    if not await _is_group_admin(update):
        await msg.reply_text("Only group admins can use this command.")
        return

    async with session_scope() as session:
        group = await session.get(Group, chat.id)
        if group is None or not group.stripe_subscription_id:
            await msg.reply_text("No active subscription found for this group.")
            return
        sub_id = group.stripe_subscription_id

    try:
        import asyncio
        import stripe as stripe_lib
        from .config import settings
        stripe_lib.api_key = settings.stripe_secret_key
        await asyncio.to_thread(stripe_lib.Subscription.cancel, sub_id)
        await msg.reply_text("✅ Subscription cancelled. Your group will revert to the free plan.")
    except Exception as e:
        log.error("unsubscribe_failed", err=str(e))
        await msg.reply_text("Failed to cancel subscription. Please try again later.")
