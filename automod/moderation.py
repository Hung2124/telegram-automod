"""Group message moderation pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from .classifier import classify, Verdict
from .db import session_scope
from .models import AuditLog, Group, GroupMember, User
from .quota import check_and_increment

log = structlog.get_logger()


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.text:
        return
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    # 1. Load group from DB; skip if not found or inactive
    async with session_scope() as session:
        group = await session.get(Group, chat.id)
        if group is None or not group.is_active:
            return

        plan = group.plan
        rules = group.rules_text or ""
        thresholds: dict[str, str] = group.action_thresholds or {
            "high": "delete_and_mute",
            "medium": "delete",
            "low": "warn",
        }
        mute_minutes = group.mute_duration_minutes or 60

    # 2. Quota check — silently skip if exceeded
    allowed = await check_and_increment(chat.id, plan)
    if not allowed:
        log.info("quota_exceeded", chat_id=chat.id, plan=plan)
        return

    # 3. Classify
    verdict: Verdict = await classify(msg.text, group_rules=rules)
    log.info(
        "classified",
        chat_id=chat.id,
        user_id=user.id,
        category=verdict.category,
        severity=verdict.severity,
        is_violation=verdict.is_violation,
        confidence=verdict.confidence,
    )

    # 4. Determine action
    action = "noop"
    if verdict.is_violation and verdict.confidence >= 0.6:
        action = thresholds.get(verdict.severity, "noop")

    # 5. Execute action
    try:
        if action == "delete_and_mute":
            await msg.delete()
            until = datetime.now(timezone.utc) + timedelta(minutes=mute_minutes)
            await context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                permissions={"can_send_messages": False},  # type: ignore[arg-type]
                until_date=until,
            )
        elif action == "delete":
            await msg.delete()
        elif action == "warn":
            await msg.reply_text(
                f"⚠️ @{user.username or user.first_name}: this message may violate group rules "
                f"({verdict.category}). Reason: {verdict.reason}"
            )
    except Exception as e:
        log.error("action_failed", action=action, err=str(e))

    # 6. Write to audit_log; upsert user + group_member; update warn_count
    async with session_scope() as session:
        # Upsert user
        db_user = await session.get(User, user.id)
        if db_user is None:
            session.add(User(
                id=user.id,
                username=user.username,
                first_name=user.first_name or "",
            ))
        else:
            db_user.username = user.username
            db_user.first_name = user.first_name or ""
        await session.flush()

        # Upsert group_member
        res = await session.execute(
            select(GroupMember).where(
                GroupMember.group_id == chat.id,
                GroupMember.user_id == user.id,
            )
        )
        member = res.scalar_one_or_none()
        if member is None:
            member = GroupMember(group_id=chat.id, user_id=user.id, role="member")
            session.add(member)
            await session.flush()

        if action == "warn":
            member.warn_count = (member.warn_count or 0) + 1

        # Write audit log
        entry = AuditLog(
            group_id=chat.id,
            user_id=user.id,
            message_text=msg.text[:1000],
            verdict_category=verdict.category,
            verdict_severity=verdict.severity,
            verdict_confidence=verdict.confidence,
            verdict_reason=verdict.reason,
            action_taken=action,
        )
        session.add(entry)
